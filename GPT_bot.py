import random
from datetime import datetime
from telegram import Update
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

# Пулы ответов
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
    await update.message.reply_text(
        "Привет! Я магический шар. Задавай вопросы, и я дам ответ. "
        "Контекст сохраняется в течение одного дня."
    )

# Команда /help
async def help_command(update: Update, context):
    await update.message.reply_text(
        "Задавай вопросы, и я отвечу в стиле магического шара. "
        "Мои ответы могут быть лаконичными, но я стараюсь учитывать контекст в течение дня."
    )

# Генерация ответа с учетом контекста и OpenAI
async def generate_response(question, user_id):
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

    # Проверка на конкретные вопросы
    if any(kw in question.lower() for kw in ["нарисовать", "написать", "сделать"]):
        specific_responses = [
            "Нарисуй закат.", "Попробуй изобразить что-то абстрактное.", 
            "Напиши короткий рассказ.", "Создай что-нибудь минималистичное."
        ]
        response = random.choice(specific_responses)
    else:
        # Генерация нового ответа через OpenAI
        try:
            openai_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Отвечай как магический шар: лаконично, иногда холодно, иногда нейтрально, иногда положительно."},
                    {"role": "user", "content": question}
                ]
            )
            response = openai_response["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Ошибка OpenAI: {e}")
            response = random.choice(NEGATIVE_RESPONSES + POSITIVE_RESPONSES + NEUTRAL_RESPONSES)

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

# Обработка сообщений
async def handle_message(update: Update, context):
    user_message = update.message.text
    user_id = update.message.from_user.id

    # Генерация ответа
    response = await generate_response(user_message, user_id)

    # Отправляем ответ пользователю
    await update.message.reply_text(response)

# Настройка бота
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск polling
    application.run_polling()

if __name__ == "__main__":
    main()