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
import regex

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

def is_pure_text(text):
    """Проверяет, состоит ли сообщение только из букв, цифр, пробелов и знаков препинания."""
    return bool(regex.fullmatch(r"[\p{L}\p{N}\p{P}\s]+", text))  # `\p{L}` - буквы, `\p{N}` - цифры, `\p{P}` - знаки

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

# Отправляет клавиатуру с кнопками выбора души
async def set_soul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает список доступных душ"""
    telegram_id = update.message.from_user.id
    user_data = database.get_user(telegram_id)
    if not user_data:
        await update.message.reply_text("Ошибка доступа к данным.")
        return

    user_id = user_data[0]
    unlocked_souls = database.get_unlocked_souls(user_id)

    if not unlocked_souls:
        await update.message.reply_text("У тебя пока нет разблокированных душ. Введи название души, чтобы разблокировать её!")
        return

    # Генерируем кнопки только для доступных душ
    keyboard = [[KeyboardButton(soul)] for soul in unlocked_souls]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text("Выбери душу:", reply_markup=reply_markup)

# Обрабатывает выбор души из клавиатуры
async def select_soul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие на кнопку с выбором души."""
    soul_choice = update.message.text.lower().strip()
    telegram_id = update.message.from_user.id

    user_data = database.get_user(telegram_id)
    if not user_data:
        await update.message.reply_text("Ошибка доступа к данным.")
        return

    user_id = user_data[0]
    unlocked_souls = database.get_unlocked_souls(user_id)

    if soul_choice in unlocked_souls:
        context.user_data["mode"] = soul_choice
        soul_name = config["characters"][soul_choice]["name"]
        await update.message.reply_text(f"Теперь ты говоришь с {soul_name}!")
    else:
        await update.message.reply_text("Ты ещё не разблокировал эту душу. Введи её название, чтобы добавить в список.")

# Выбор души через команду /soul имя_души
async def set_soul_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меняет душу вручную, если передан аргумент."""
    characters = config.get("characters", {})
    if not characters:
        await update.message.reply_text("Ошибка: список душ не загружен.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /soul имя_души (oracle, trainer, philosopher, hooligan)")
        return

    soul_choice = context.args[0].lower().strip()

    if soul_choice in characters:
        context.user_data["mode"] = soul_choice
        soul_name = characters[soul_choice]["name"]
        await update.message.reply_text(f"Теперь ты говоришь с {soul_name}!")
        logger.info(f"Пользователь {update.message.from_user.id} выбрал душу: {soul_choice}")
    else:
        await update.message.reply_text("Такой души нет. Используйте /souls для выбора.")

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

# Генерация ответа для Душ
async def generate_soul_response(question, mode):
    """Генерирует ответ от выбранной души."""
    soul = config.get("characters", {}).get(mode, config.get("characters", {}).get("oracle", {}))
    soul_name = soul.get("name", "Неизвестная Душа")
    soul_description = soul.get("description", "Отвечай в своей уникальной манере.")

    logger.info(f"Запрос в OpenAI для {soul_name}: {question}")
    try:
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0.7,  # Добавили немного случайности
            messages=[
                {"role": "system", "content": soul_description},
                {"role": "user", "content": question}
            ]
        )
        response = openai_response["choices"][0]["message"]["content"].strip()
        logger.info(f"Ответ {soul_name}: {response}")
        return f"{soul_name} говорит:\n{response}"
    except openai.error.OpenAIError as e:
        logger.error(f"Ошибка OpenAI: {e}")
        return f"{soul_name} говорит:\n{config['messages']['oracle_error']}"


# Обработка входящих сообщений (включая выбор души)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.lower().strip()
    telegram_id = update.message.from_user.id

    # Получаем `id` пользователя
    user_data = database.get_user(telegram_id)
    if not user_data:
        database.add_user(telegram_id, update.message.from_user.username)
        user_data = database.get_user(telegram_id)
    if not user_data:
        await update.message.reply_text("Ошибка доступа к данным. Попробуйте позже.")
        return

    user_id = user_data[0]  # ID пользователя в базе

    # Проверяем, является ли сообщение названием души
    if user_message in config["characters"]:
        unlocked_souls = database.get_unlocked_souls(user_id)

        if user_message not in unlocked_souls:
            if database.unlock_soul(user_id, user_message):
                await update.message.reply_text(f"Ты разблокировал душу: {config['characters'][user_message]['name']}!")
            else:
                await update.message.reply_text("Эта душа уже у тебя есть.")
        return  # Завершаем обработку, так как душа была добавлена

    # Проверяем, что сообщение состоит только из текста
    if not is_pure_text(user_message):
        return  # Игнорируем сообщения с эмодзи, вложениями и т.д.

    logger.info(f"Получено сообщение от пользователя {telegram_id}: {user_message}")

    # Получаем статус подписки и лимиты
    is_premium = user_data[3] if user_data[3] is not None else False
    free_answers_left = user_data[4] if user_data[4] is not None else 3

    # Если лимит бесплатных запросов исчерпан
    if not is_premium and free_answers_left <= 0:
        logger.info(f"Пользователь {telegram_id} исчерпал лимит бесплатных ответов.")
        await update.message.reply_text("Ваши бесплатные запросы закончились. Оформите подписку, чтобы продолжить.")
        return

    # Уменьшаем количество бесплатных запросов
    if not is_premium:
        database.decrease_free_answers(telegram_id)
        user_data = database.get_user(telegram_id)
        free_answers_left = user_data[4] if user_data[4] is not None else 0
        logger.info(f"После уменьшения у {telegram_id} осталось {free_answers_left} бесплатных запросов")

    # Если осталось мало бесплатных запросов – предупреждаем
    if not is_premium and free_answers_left in [1, 2]:
        await update.message.reply_text(f"У вас осталось {free_answers_left} бесплатных запроса.")

    # Определяем текущий режим (по умолчанию – Оракул)
    mode = context.user_data.get("mode", "oracle")

    # Обрабатываем сообщение в зависимости от режима
    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message, telegram_id, context)
    else:
        response = await generate_soul_response(user_message, mode)

    # Логируем сообщение и отправляем ответ
    database.log_message(telegram_id, user_message, response, mode)
    logger.info(f"Финальный ответ пользователю {telegram_id}: {response}")
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


# Обновление хэндлеров в `main()`
def main():
    logger.info("Запуск бота...")
    application = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("oracle", oracle))
    application.add_handler(CommandHandler("magicball", magicball))

    application.add_handler(CommandHandler("souls", set_soul))  # Меню с кнопками выбора души
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))  # Обработка сообщений

    try:
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка в основном цикле бота: {e}")

if __name__ == "__main__":
    main()
