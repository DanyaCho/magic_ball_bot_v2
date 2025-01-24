import random
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
from dotenv import load_dotenv
import os
import logging

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

# Пулы ответов для Магического Шара
NEGATIVE_RESPONSES = [
    "Нет.", "Не стоит.", "Думаю, хватит.",
    "Я уже сказал нет.", "Определенно нет.",
    "Хватит уже."
]
POSITIVE_RESPONSES = [
    "Да!", "Почему бы нет?", "Конечно!",
    "Давай!", "Определенно."
]
NEUTRAL_RESPONSES = [
    "Может быть.", "Зависит от ситуации.",
    "Сложно сказать.", "Тебе решать."
]
EXTRA_RESPONSES = [
    "Подумай еще раз.", "Решение за тобой.",
    "Ты сам знаешь ответ."
]

# Ответы для скрытого режима "медитация"
MEDITATION_RESPONSES = [
    "Похуй!", "Похуй!", "Тоже похуй!", "Вообще похую!"
]

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[KeyboardButton("Оракул"), KeyboardButton("Магический шар")]]
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Выберите режим: Оракул или Магический шар.", reply_markup=reply_markup
    )
    context.user_data.clear()  # Сброс контекста для пользователя при запуске

# Команда /oracle
async def oracle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "oracle"
    await update.message.reply_text("Режим Оракула активирован. Задавайте вопросы.")

# Команда /magicball
async def magicball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "magic_ball"
    await update.message.reply_text("Режим Магического шара активирован. Задавайте вопросы.")

# Генерация ответа для Магического Шара
async def generate_magic_ball_response(question, user_id, context):
    now = datetime.now()

    # Очистка контекста через день
    if "last_interaction_date" in context.user_data:
        last_date = context.user_data["last_interaction_date"]
        if now.date() != last_date:
            context.user_data.clear()

    # Если вопрос повторный
    if "last_question" in context.user_data and question.lower() in ["точно?", "или?", "правда?", "ты уверен?"]:
        return f"{context.user_data['last_response']} (я повторяю)."

    # Генерация нового ответа
    chosen_tone = random.choice(["негативный", "позитивный", "нейтральный"])
    if chosen_tone == "негативный":
        response = random.choice(NEGATIVE_RESPONSES)
    elif chosen_tone == "позитивный":
        response = random.choice(POSITIVE_RESPONSES)
    else:
        response = random.choice(NEUTRAL_RESPONSES)

    # Редкий случай добавления дополнительной фразы
    if random.random() < 0.1:  # 10% вероятность
        response += " " + random.choice(EXTRA_RESPONSES)

    # Сохранение контекста
    context.user_data["last_question"] = question.lower()
    context.user_data["last_response"] = response
    context.user_data["last_interaction_date"] = now.date()

    return response

# Генерация ответа для Оракула
async def generate_oracle_response(question):
    try:
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "Ты Оракул. Отвечай загадочно, иногда надменно, с элементами мистики. "
                    "Твои ответы должны быть лаконичными, но содержать скрытый смысл. "
                    "Не объясняй детали, но вдохновляй размышлять. "
                    "Иногда используй метафоры и философские намеки."
                )},
                {"role": "user", "content": question}
            ]
        )
        response = openai_response["choices"][0]["message"]["content"]
        return response.strip()
    except openai.error.OpenAIError as e:
        logging.error(f"Ошибка OpenAI: {e}")
        return "Звезды молчат. Попробуй позже."

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.lower()

    # Скрытый режим "медитация"
    if context.user_data.get("mode") == "meditation":
        step = context.user_data.get("meditation_step", 0)
        if step < len(MEDITATION_RESPONSES):
            response = MEDITATION_RESPONSES[step]
            context.user_data["meditation_step"] += 1
            if context.user_data["meditation_step"] >= len(MEDITATION_RESPONSES):
                context.user_data["mode"] = None  # Завершаем скрытый режим
                await update.message.reply_text(response)
                await update.message.reply_text("Режим медитации завершён.")
            else:
                await update.message.reply_text(response)
            return

    # Активация скрытого режима
    if user_message == "медитация":
        context.user_data["mode"] = "meditation"
        context.user_data["meditation_step"] = 0
        await update.message.reply_text("Режим медитации активирован.")
        return

    # Обычные режимы
    if user_message == "магический шар":
        context.user_data["mode"] = "magic_ball"
        await update.message.reply_text("Вы выбрали режим Магического шара. Задавайте вопросы.")
    elif user_message == "оракул":
        context.user_data["mode"] = "oracle"
        await update.message.reply_text("Вы выбрали режим Оракула. Задавайте вопросы.")
    else:
        mode = context.user_data.get("mode", "magic_ball")
        if mode == "magic_ball":
            response = await generate_magic_ball_response(user_message, update.message.from_user.id, context)
        else:
            response = await generate_oracle_response(user_message)

        await update.message.reply_text(response)

# Настройка команд меню
async def set_commands(application):
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("oracle", "Режим Оракула"),
        BotCommand("magicball", "Режим Магического шара")
    ]
    await application.bot.set_my_commands(commands)

# Настройка бота
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Создаем JobQueue и добавляем задачу для установки команд
    job_queue = application.job_queue
    job_queue.run_once(lambda _: set_commands(application), 0)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск polling с обработкой исключений
    try:
        application.run_polling()
    except Exception as e:
        logging.error(f"Ошибка в основном цикле бота: {e}")

if __name__ == "__main__":
    main()