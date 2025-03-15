async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.lower()
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    # Проверяем, есть ли у пользователя уже разблокированные души
    unlocked_souls = database.get_user_souls(user_id)

    # Проверяем, находится ли бот в режиме выбора души
    if context.user_data.get("mode") == "soul_selection":
        if user_message in config["characters"]:
            if user_message not in unlocked_souls:
                if database.unlock_soul(user_id, user_message):
                    unlocked_souls.append(user_message)
                    context.user_data["mode"] = user_message
                    await update.message.reply_text(f"Ты разблокировал душу: {config['characters'][user_message]['name']}!\nТеперь ты говоришь с ней!")
                else:
                    await update.message.reply_text("Не удалось разблокировать душу.")
                return

            # Если душа уже разблокирована, переключаемся на неё
            context.user_data["mode"] = user_message
            await update.message.reply_text(f"Теперь ты говоришь с {config['characters'][user_message]['name']}!")
        else:
            await update.message.reply_text("Такой души нет. Пожалуйста, выбери существующую душу.")
        return

    # Если сообщение не является названием души, обрабатываем его как обычный вопрос
    mode = context.user_data.get("mode", "oracle")  # По умолчанию — Оракул
    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message,import json
from datetime import datetime
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import database
import logging
import openai
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Настройка OpenAI
openai.api_key = OPENAI_API_KEY

# Логирование
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
try:
    with open("config.json", "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
except FileNotFoundError:
    logger.error("Файл config.json не найден.")
    exit(1)
except json.JSONDecodeError as e:
    logger.error(f"Ошибка разбора config.json: {e}")
    exit(1)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(config["messages"]["start"])
    logger.info(f"Пользователь {update.message.from_user.id} вызвал команду /start")

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

# Команда /buy_premium
async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = database.get_user(user_id)
    
    if not user_data:
        database.add_user(user_id, update.message.from_user.username)
        user_data = database.get_user(user_id)
    
    if user_data[3]:  # Проверка premium (3-й индекс в кортежах users)
        await update.message.reply_text("У тебя уже есть премиум!")
        return
    
    await update.message.reply_text("Чтобы оформить подписку, перейди по ссылке: https://example.com/payment")
    logger.info(f"Пользователь {user_id} хочет купить премиум.")

# Генерация ответа
async def generate_response(user_message, mode):
    prompt = config["characters"][mode]["description"]
    try:
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt},
                      {"role": "user", "content": user_message}]
        )
        return openai_response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {e}")
        return "Произошла ошибка. Попробуйте позже."

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_message = update.message.text.strip().lower()

    user_data = database.get_user(user_id)
    if not user_data:
        database.add_user(user_id, update.message.from_user.username)
        user_data = database.get_user(user_id)

    free_answers = user_data[4]  # 4-й индекс — оставшиеся бесплатные ответы
    premium = user_data[3]  # 3-й индекс — статус подписки

    # Проверяем, есть ли бесплатные ответы
    if not premium and free_answers <= 0:
        await update.message.reply_text("У вас закончились бесплатные ответы! Оформите подписку: /buy_premium")
        return

    # Определяем режим
    mode = context.user_data.get("mode", "oracle")
    response = await generate_response(user_message, mode)
    database.log_message(user_id, user_message, response, mode)
    
    if not premium:
        database.decrease_free_answers(user_id)
    
    await update.message.reply_text(response)

# Настройка команд
async def set_commands(application):
    commands = [
        BotCommand("start", "Начать"),
        BotCommand("oracle", "Режим Оракула"),
        BotCommand("magicball", "Режим Магического шара"),
        BotCommand("buy_premium", "Оформить подписку")
    ]
    await application.bot.set_my_commands(commands)

# Запуск бота
def main():
    application = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("oracle", oracle))
    application.add_handler(CommandHandler("magicball", magicball))
    application.add_handler(CommandHandler("buy_premium", buy_premium))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == "__main__":
    main()
