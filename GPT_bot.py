import random
import json
from datetime import datetime
from telegram import Update, BotCommand, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
from dotenv import load_dotenv
import os
import logging
import database

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Установка ключа OpenAI
openai.api_key = OPENAI_API_KEY

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации из config.json
try:
    with open("config.json", "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
        logger.info("Конфигурация успешно загружена.")
except FileNotFoundError:
    logger.error("Файл config.json не найден.")
    exit(1)
except json.JSONDecodeError as e:
    logger.error(f"Ошибка при разборе config.json: {e}")
    exit(1)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        config["messages"]["start"]
    )
    logger.info(f"Пользователь {update.message.from_user.id} вызвал команду /start")
    # Если нужно сбросить историю, очищаем только часть данных, не трогая режим
    current_mode = context.user_data.get("mode")
    context.user_data.clear()
    if current_mode:
        context.user_data["mode"] = current_mode

# Команда /oracle
async def oracle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "oracle"
    await update.message.reply_text(config["messages"]["oracle_mode"])
    logger.info(f"Пользователь {update.message.from_user.id} переключился в режим Оракула")

# Команда /magicball
async def magicball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "magic_ball"
    await update.message.reply_text(config["messages"]["magic_ball_mode"])
    logger.info(f"Пользователь {update.message.from_user.id} переключился в режим Магического шара")

# Генерация ответа для Магического Шара
async def generate_magic_ball_response(question, telegram_id, context):
    now = datetime.now()

    # Очистка данных магического шара через новый день (удаляем только специфичные ключи)
    if "last_interaction_date" in context.user_data:
        last_date = context.user_data["last_interaction_date"]
        if now.date() != last_date:
            for key in ["last_question", "last_response", "last_interaction_date"]:
                context.user_data.pop(key, None)

    # Если вопрос повторный (срабатывает для определённых триггеров)
    if "last_question" in context.user_data and question.lower() in config["repeat_triggers"]:
        return f"{context.user_data['last_response']} (я повторяю)."

    # Генерация нового ответа
    chosen_tone = random.choice(["негативный", "позитивный", "нейтральный"])
    if chosen_tone == "негативный":
        response = random.choice(config["magic_ball_responses"]["negative"])
    elif chosen_tone == "позитивный":
        response = random.choice(config["magic_ball_responses"]["positive"])
    else:
        response = random.choice(config["magic_ball_responses"]["neutral"])

    logger.info(f"Ответ Магического Шара для {telegram_id}: {response}")

    # Редкий случай добавления дополнительной фразы (10% вероятность)
    if random.random() < 0.1:
        response += " " + random.choice(config["magic_ball_responses"]["extra"])

    # Сохранение данных для повторных вопросов
    context.user_data["last_question"] = question.lower()
    context.user_data["last_response"] = response
    context.user_data["last_interaction_date"] = now.date()

    return response

# Генерация ответа для Оракула
async def generate_oracle_response(question):
    logger.info(f"Запрос в OpenAI для Оракула: {question}")
    try:
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": config["oracle_description"]},
                {"role": "user", "content": question}
            ]
        )
        response = openai_response["choices"][0]["message"]["content"]
        logger.info(f"Ответ Оракула: {response.strip()}")
        return response.strip()
    except openai.error.OpenAIError as e:
        logger.error(f"Ошибка OpenAI: {e}")
        return config["messages"]["oracle_error"]

# Обработка входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.lower()
    logger.info(f"Получено сообщение от пользователя {update.message.from_user.id}: {user_message}")

    # Получаем информацию о пользователе из базы
    telegram_id = update.message.from_user.id
    user_data = database.get_user(telegram_id)

    if not user_data:
        # Если пользователя нет в базе – добавляем
        database.add_user(telegram_id, update.message.from_user.username)
        user_data = database.get_user(telegram_id)

    # Если по какой-то причине `get_user` вернул None, сразу возвращаем ошибку
    if not user_data:
        logger.error(f"Ошибка получения данных пользователя {telegram_id} после добавления!")
        await update.message.reply_text("Ошибка доступа к данным. Попробуйте позже.")
        return

    is_premium = user_data[3] if user_data[3] is not None else False  # Если None, значит не премиум
    free_answers_left = user_data[4] if user_data[4] is not None else 3  # Если None, ставим 3 бесплатных запроса

    # Если у пользователя нет подписки и закончились бесплатные ответы
    if not is_premium and free_answers_left <= 0:
        logger.info(f"Пользователь {telegram_id} исчерпал лимит бесплатных ответов.")
        await update.message.reply_text(
            "Ваши бесплатные запросы закончились. Оформите подписку, чтобы продолжить пользоваться ботом."
        )
        return  # Прекращаем обработку сообщения

    # Если у пользователя нет подписки – уменьшаем счетчик
    if not is_premium:
        database.decrease_free_answers(user_id)  # Обновляем в БД
        user_data = database.get_user(user_id)  # Получаем свежие данные
        free_answers_left = user_data[4]  # Обновляем локально

    # Если осталось мало бесплатных запросов – предупреждаем
    if not is_premium and free_answers_left in [1, 2]:
        await update.message.reply_text(
            f"У вас осталось {free_answers_left} бесплатных запроса. После этого доступ будет ограничен."
        )

    # Проверка на активацию скрытого режима
    if user_message == config["hidden_mode_trigger"]:
        # Сохраняем предыдущий режим для последующего восстановления
        context.user_data["previous_mode"] = context.user_data.get("mode", "magic_ball")
        context.user_data["mode"] = "hidden"
        context.user_data["hidden_mode_index"] = 0
        await update.message.reply_text(config["messages"]["hidden_mode_activated"])
        return

    mode = context.user_data.get("mode", "magic_ball")
    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message, update.message.from_user.id, context)
    elif mode == "oracle":
        response = await generate_oracle_response(user_message)
    elif mode == "hidden":
        hidden_responses = config["hidden_mode_responses"]
        index = context.user_data.get("hidden_mode_index", 0)
        response = hidden_responses[index]
        context.user_data["hidden_mode_index"] = (index + 1) % len(hidden_responses)
        # После последнего ответа в скрытом режиме восстанавливаем предыдущий режим
        if index == len(hidden_responses) - 1:
            restored_mode = context.user_data.get("previous_mode", "magic_ball")
            context.user_data["mode"] = restored_mode
            context.user_data.pop("previous_mode", None)
            await update.message.reply_text(config["messages"]["hidden_mode_deactivated"])
    else:
        response = config["messages"]["unknown_mode"]

    # Вставляем перед отправкой сообщения пользователю
    database.log_message(update.message.from_user.id, user_message, response, mode)

    logger.info(f"Финальный ответ пользователю {update.message.from_user.id}: {response}")
    await update.message.reply_text(response)

# Настройка команд меню
async def set_commands(application):
    logger.info("Бот успешно запущен и готов к работе.")
    try:
        commands = [BotCommand(cmd["command"], cmd["description"]) for cmd in config["commands"]]
        await application.bot.set_my_commands(commands)
        logging.info("Команды успешно установлены.")
    except Exception as e:
        logging.error(f"Ошибка при установке команд: {e}")

# Настройка и запуск бота
def main():
    logger.info("Запуск бота...")
    application = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("oracle", oracle))
    application.add_handler(CommandHandler("magicball", magicball))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    try:
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка в основном цикле бота: {e}")

if __name__ == "__main__":
    main()
