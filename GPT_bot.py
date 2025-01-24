import random
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import openai
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Установка ключа OpenAI
openai.api_key = OPENAI_API_KEY

# История вопросов (контекст с временными метками)
user_context = {}

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

# Команда /start
async def start(update: Update, context):
    buttons = [[KeyboardButton("Оракул"), KeyboardButton("Магический шар")]]
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Выберите режим: Оракул или Магический шар.", reply_markup=reply_markup
    )

# Генерация ответа для Магического Шара
async def generate_magic_ball_response(question, user_id):
    now = datetime.now()

    # Очистка контекста через день
    if user_id in user_context:
        if now.date() != user_context[user_id]["date"]:
            del user_context[user_id]

    # Если есть контекст
    if user_id in user_context:
        last_question = user_context[user_id]["last_question"]
        last_response = user_context[user_id]["last_response"]

        # Если вопрос связан с предыдущим
        if question.lower() in ["точно?", "или?", "правда?", "ты уверен?"]:
            return f"{last_response} (я повторяю)."

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
    user_context[user_id] = {
        "last_question": question.lower(),
        "last_response": response,
        "date": now.date(),
    }
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
    except Exception as e:
        print(f"Ошибка OpenAI: {e}")
        return "Звезды молчат. Попробуй позже."

# Обработка сообщений
async def handle_message(update: Update, context):
    user_message = update.message.text
    user_id = update.message.from_user.id

    if user_message == "Магический шар":
        context.user_data["mode"] = "magic_ball"
        await update.message.reply_text("Вы выбрали режим Магического шара. Задавайте вопросы.")
    elif user_message == "Оракул":
        context.user_data["mode"] = "oracle"
        await update.message.reply_text("Вы выбрали режим Оракула. Задавайте вопросы.")
    else:
        mode = context.user_data.get("mode", "magic_ball")
        if mode == "magic_ball":
            response = await generate_magic_ball_response(user_message, user_id)
        else:
            response = await generate_oracle_response(user_message)

        await update.message.reply_text(response)

# Настройка бота
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск polling
    application.run_polling()

if __name__ == "__main__":
    main()
