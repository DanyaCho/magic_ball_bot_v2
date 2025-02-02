import random
import json
from datetime import datetime
from telegram import Update, BotCommand
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

# Загрузка конфигурации из JSON
print("🔄 Начинаем загрузку config.json")
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)
    print("✅ Загруженный config:", config)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Unknown"
    database.add_user(user_id, username)
    await update.message.reply_text(config["messages"]["start"])
    context.user_data.clear()

# Команда /oracle
async def oracle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "oracle"
    await update.message.reply_text(config["messages"]["oracle_mode"])

# Команда /magicball
async def magicball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "magic_ball"
    await update.message.reply_text(config["messages"]["magic_ball_mode"])

# Генерация ответа для Магического Шара
async def generate_magic_ball_response(question, user_id, context):
    now = datetime.now()
    user_data = database.get_user(user_id)

    if not user_data:
        username = "Unknown"
        database.add_user(user_id, username)
        user_data = database.get_user(user_id)

    chosen_tone = random.choice(["negative", "positive", "neutral"])
    response = random.choice(config["magic_ball_responses"][chosen_tone])

    if random.random() < 0.1:
        response += " " + random.choice(config["magic_ball_responses"]["extra"])
    
    return response

# Генерация ответа для Оракула
async def generate_oracle_response(question, user_id):
    user_data = database.get_user(user_id)
    
    if not user_data:
        username = "Unknown"
        database.add_user(user_id, username)
        user_data = database.get_user(user_id)
    
    if not user_data["premium"] and user_data["free_answers_remaining"] <= 0:
        return config["messages"]["oracle_error"]
    
    try:
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": config["oracle_description"]},
                {"role": "user", "content": question}
            ]
        )
        response = openai_response["choices"][0]["message"]["content"].strip()
        database.decrease_free_answers(user_id)
        return response
    except openai.error.OpenAIError as e:
        logging.error(f"Ошибка OpenAI: {e}")
        return config["messages"]["oracle_error"]

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.message.from_user.id
    
    if user_message.lower() == config["hidden_mode_trigger"]:
        context.user_data["mode"] = "meditation"
        context.user_data["meditation_step"] = 0
        await update.message.reply_text(config["messages"]["hidden_mode_activated"])
        return
    
    mode = context.user_data.get("mode", "magic_ball")
    
    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message, user_id, context)
    elif mode == "oracle":
        response = await generate_oracle_response(user_message, user_id)
    else:
        response = config["messages"]["unknown_mode"]

    await update.message.reply_text(response)

# Настройка команд меню
async def set_commands(application):
    commands = [BotCommand(cmd["command"], cmd["description"]) for cmd in config["commands"]]
    await application.bot.set_my_commands(commands)

# Настройка бота
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("oracle", oracle))
    application.add_handler(CommandHandler("magicball", magicball))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    async def on_startup(application: Application):
        await set_commands(application)
    
    application.run_polling()

if __name__ == "__main__":
    main()
