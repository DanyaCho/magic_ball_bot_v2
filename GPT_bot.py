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

# Загрузка конфигурации из config.json
try:
    with open("config.json", "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
        logging.info("✅ Конфигурация успешно загружена.")
except FileNotFoundError:
    logging.error("❌ Файл config.json не найден.")
    exit(1)
except json.JSONDecodeError as e:
    logging.error(f"❌ Ошибка при разборе config.json: {e}")
    exit(1)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[KeyboardButton("Оракул"), KeyboardButton("Магический шар")]]
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    # Добавляем пользователя в базу (если его нет)
    database.add_user(user_id, username)
    context.user_data["mode"] = "magic_ball"  # Ставим режим по умолчанию

    logging.info(f"👤 Пользователь {username} (ID: {user_id}) начал работу, режим: Magic Ball")
    
    await update.message.reply_text(
        config["messages"]["start"], reply_markup=reply_markup
    )

# Команда /oracle
async def oracle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "oracle"
    
    # Сохранение режима в базу данных
    database.update_user_mode(update.message.from_user.id, "oracle") ###

    logging.info(f"🔮 Режим Оракула активирован для {update.message.from_user.username}")
    await update.message.reply_text(config["messages"]["oracle_mode"])

# Команда /magicball
async def magicball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "magic_ball"
    
    # Сохранение режима в базу данных
    database.update_user_mode(update.message.from_user.id, "magic_ball") ###

    logging.info(f"🎱 Режим Магического шара активирован для {update.message.from_user.username}")
    await update.message.reply_text(config["messages"]["magic_ball_mode"])

# Генерация ответа для Магического Шара
async def generate_magic_ball_response(question, user_id, context):
    now = datetime.now()

    # Очистка контекста через день
    if "last_interaction_date" in context.user_data:
        last_date = context.user_data["last_interaction_date"]
        if now.date() != last_date:
            context.user_data.clear()

    # Если вопрос повторный
    if "last_question" in context.user_data and question.lower() in config["repeat_triggers"]:
        return f"{context.user_data['last_response']} (я повторяю)."

    # Генерация нового ответа
    chosen_tone = random.choice(["negative", "positive", "neutral"])
    response = random.choice(config["magic_ball_responses"][chosen_tone])

    # Редкий случай добавления дополнительной фразы
    if random.random() < 0.1:  # 10% вероятность
        response += " " + random.choice(config["magic_ball_responses"]["extra"])

    # Сохранение контекста
    context.user_data["last_question"] = question.lower()
    context.user_data["last_response"] = response
    context.user_data["last_interaction_date"] = now.date()

    logging.info(f"🎱 Magic Ball ответил: {response}")
    return response

# Генерация ответа для Оракула
async def generate_oracle_response(question):
    try:
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": config["oracle_description"]},
                {"role": "user", "content": question}
            ]
        )
        response = openai_response["choices"][0]["message"]["content"].strip()
        logging.info(f"🔮 Oracle ответил: {response}")
        return response
    except openai.error.OpenAIError as e:
        logging.error(f"❌ Ошибка OpenAI: {e}")
        return config["messages"]["oracle_error"]

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.lower()
    user_id = update.message.from_user.id

    # Определение режима пользователя (читаем из БД)
    mode = context.user_data.get("mode", database.get_user_mode(user_id)) ###

    logging.info(f"📩 Получено сообщение: '{user_message}' | Режим: {mode}")

    if user_message == config["hidden_mode_trigger"]:
        context.user_data["mode"] = "hidden"
        context.user_data["hidden_mode_index"] = 0
        await update.message.reply_text(config["messages"]["hidden_mode_activated"])
        return

    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message, user_id, context)
    elif mode == "oracle":
        response = await generate_oracle_response(user_message)
    else:
        response = config["messages"]["unknown_mode"]

    await update.message.reply_text(response)

# Настройка команд меню
async def set_commands(application):
    commands = [BotCommand(cmd["command"], cmd["description"]) for cmd in config["commands"]]
    await application.bot.set_my_commands(commands)
    logging.info("✅ Команды успешно установлены.")

# Настройка бота
def main():
    application = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("oracle", oracle))
    application.add_handler(CommandHandler("magicball", magicball))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    try:
        application.run_polling()
    except Exception as e:
        logging.error(f"❌ Ошибка в основном цикле бота: {e}")

if __name__ == "__main__":
    main()
