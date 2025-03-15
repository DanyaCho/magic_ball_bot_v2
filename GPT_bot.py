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
openai.api_key = OPENAI_API_KEY

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
try:
    with open("config.json", "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
        logger.info("Конфигурация успешно загружена.")
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.error(f"Ошибка при загрузке config.json: {e}")
    exit(1)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(config["messages"]["start"])
    context.user_data.clear()

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
    chosen_tone = random.choice(["negative", "positive", "neutral"])
    response = random.choice(config["magic_ball_responses"].get(chosen_tone, []))
    logger.info(f"Ответ Магического Шара для {telegram_id}: {response}")
    return response

# Генерация ответа для Оракула
async def generate_oracle_response(question):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": config["characters"]["oracle"]["description"]},
                      {"role": "user", "content": question}]
        )["choices"][0]["message"]["content"].strip()
        return response
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {e}")
        return config["messages"]["oracle_error"]

# Обработка входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.strip()
    user_id = update.message.from_user.id

    # Определяем текущий режим
    mode = context.user_data.get("mode", "oracle")
    
    # Генерируем ответ
    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message, user_id, context)
    else:
        response = await generate_oracle_response(user_message)

    database.log_message(user_id, user_message, response, mode)
    await update.message.reply_text(response)

# Настройка команд
async def set_commands(application):
    try:
        commands = [
            BotCommand("start", "Начать работу"),
            BotCommand("oracle", "Переключиться в режим Оракула"),
            BotCommand("magicball", "Переключиться в режим Магического шара")
        ]
        await application.bot.set_my_commands(commands)
        logging.info("Команды успешно установлены.")
    except Exception as e:
        logging.error(f"Ошибка при установке команд: {e}")

# Основной запуск бота
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
