import random
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import openai
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Set OpenAI API key
openai.api_key = OPENAI_API_KEY

# User context storage
user_context = {}

# Answer pools
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

# Start command
async def start(update: Update, context):
    keyboard = [
        [
            InlineKeyboardButton("Оракул", callback_data="oracle"),
            InlineKeyboardButton("Магический шар", callback_data="magic_ball")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! Выберите режим работы:", reply_markup=reply_markup
    )

# Help command
async def help_command(update: Update, context):
    await update.message.reply_text(
        "Выберите режим работы: \n"
        "- Оракул: подробные ответы от GPT\n"
        "- Магический шар: предустановленные ответы."
    )

# Generate Magic Ball response
async def generate_magic_ball_response(question, user_id):
    now = datetime.now()

    # Clear context daily
    if user_id in user_context:
        if now.date() != user_context[user_id]["date"]:
            del user_context[user_id]

    # If context exists
    if user_id in user_context:
        last_question = user_context[user_id]["last_question"]
        last_response = user_context[user_id]["last_response"]

        # If the question is related to the last one
        if question.lower() in ["точно?", "или?", "правда?", "ты уверен?"]:
            return f"{last_response} (я повторяю)."

    # Generate a new response
    chosen_tone = random.choice(["позитивный", "нейтральный", "негативный"])
    if chosen_tone == "негативный":
        response = random.choice(NEGATIVE_RESPONSES)
    elif chosen_tone == "позитивный":
        response = random.choice(POSITIVE_RESPONSES)
    else:
        response = random.choice(NEUTRAL_RESPONSES)

    # Rarely add an extra phrase
    if random.random() < 0.1:  # 10% chance
        response += " " + random.choice(EXTRA_RESPONSES)

    # Save context
    user_context[user_id] = {
        "last_question": question.lower(),
        "last_response": response,
        "date": now.date(),
    }
    return response

# Generate Oracle response
async def generate_oracle_response(question):
    try:
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Отвечай как мудрый оракул: подробно и логично."},
                {"role": "user", "content": question}
            ]
        )
        response = openai_response["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Ошибка OpenAI: {e}")
        response = "Извините, я не могу ответить на этот вопрос сейчас."

    return response

# Handle messages
async def handle_message(update: Update, context):
    user_message = update.message.text
    user_id = update.message.from_user.id
    mode = context.user_data.get("mode", "magic_ball")

    # Generate response based on mode
    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message, user_id)
    else:
        response = await generate_oracle_response(user_message)

    # Send response to the user
    await update.message.reply_text(response)

# Handle mode selection
async def handle_mode_selection(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "oracle":
        context.user_data["mode"] = "oracle"
        await query.edit_message_text("Режим Оракул активирован. Задавайте ваши вопросы.")
    elif query.data == "magic_ball":
        context.user_data["mode"] = "magic_ball"
        await query.edit_message_text("Режим Магический шар активирован. Задавайте ваши вопросы.")

# Main function
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(handle_mode_selection))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start polling
    application.run_polling()

if __name__ == "__main__":
    main()
