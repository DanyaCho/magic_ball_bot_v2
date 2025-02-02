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

# Установка ключа OpenAI
openai.api_key = OPENAI_API_KEY

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Подключение к базе данных
db = database

# Загрузка ответов и текстов из JSON
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    database.add_user(user_id)
    await update.message.reply_text(responses["start_message"])
    context.user_data.clear()

# Команда /oracle
async def oracle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "oracle"
    await update.message.reply_text(responses["oracle_mode"])

# Команда /magicball
async def magicball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "magic_ball"
    await update.message.reply_text(responses["magic_ball_mode"])

# Генерация ответа для Магического Шара
async def generate_magic_ball_response(question, user_id, context):
    now = datetime.now()
    user_data = database.get_user(user_id) or {}
    
    if "last_interaction_date" in user_data and now.date() != user_data["last_interaction_date"]:
        database.reset_user_responses(user_id)

    if "last_question" in user_data and question.lower() in responses["repeat_questions"]:
        return f"{user_data['last_response']} (я повторяю)."

    chosen_tone = random.choice(["negative", "positive", "neutral"])
    response = random.choice(responses["magic_ball_responses"][chosen_tone])

    if random.random() < 0.1:
        response += " " + random.choice(responses["extra_responses"])

    database.update_user_response(user_id, question.lower(), response)
    return response

# Генерация ответа для Оракула
async def generate_oracle_response(question, user_id):
    user_data = database.get_user(user_id) or {}

    if not user_data.get("is_premium") and user_data.get("free_responses", 0) <= 0:
        return responses["oracle_no_credits"]
    
    try:
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": responses["oracle_prompt"]},
                {"role": "user", "content": question}
            ]
        )
        response = openai_response["choices"][0]["message"]["content"].strip()
        database.decrement_free_responses(user_id)
        return response
    except openai.error.OpenAIError as e:
        logging.error(f"Ошибка OpenAI: {e}")
        return responses["oracle_error"]

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.message.from_user.id
    
    if user_message.lower() == "медитация":
        context.user_data["mode"] = "meditation"
        context.user_data["meditation_step"] = 0
        await update.message.reply_text(responses["meditation_start"])
        return
    
    mode = context.user_data.get("mode", "magic_ball")
    
    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message, user_id, context)
    elif mode == "oracle":
        response = await generate_oracle_response(user_message, user_id)
    elif mode == "meditation":
        step = context.user_data.get("meditation_step", 0)
        if step < len(responses["meditation_responses"]):
            response = responses["meditation_responses"][step]
            context.user_data["meditation_step"] += 1
        else:
            context.user_data["mode"] = "magic_ball"
            response = responses["meditation_end"]
    else:
        response = responses["unknown_command"]

    await update.message.reply_text(response)

# Настройка команд меню
async def set_commands(application):
    commands = [
        BotCommand("start", responses["menu_start"]),
        BotCommand("oracle", responses["menu_oracle"]),
        BotCommand("magicball", responses["menu_magicball"]),
    ]
    await application.bot.set_my_commands(commands)

# Настройка бота
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("oracle", oracle))
    application.add_handler(CommandHandler("magicball", magicball))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def on_startup():
        await set_commands(application)

    # Запускаем бота
    try:
        application.initialize()  # Инициализация бота
        application.post_init(on_startup)  # Вызываем on_startup
        application.run_polling()  # Запуск поллинга
    except Exception as e:
        logging.error(f"Ошибка в основном цикле бота: {e}")

if __name__ == "__main__":
    main()
