import json
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import database

# Получение токена из переменной окружения
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Необходимо установить переменную окружения TELEGRAM_BOT_TOKEN")

# Создание приложения с использованием полученного токена
app = ApplicationBuilder().token(TOKEN).build()

# Загружаем конфигурацию из файла config.json (переименуйте, если нужно)
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# Константы для лимитов
FREE_QUESTIONS_PER_PERIOD = 5        # Бесплатный лимит: 5 вопросов
FREE_PERIOD_DAYS = 30                # на 30 дней
PREMIUM_QUESTIONS_PER_DAY = 20       # Платный лимит: 20 вопросов
PREMIUM_PERIOD_HOURS = 24            # сброс лимита каждые 24 часа

def generate_oracle_answer(question: str) -> str:
    """
    Функция генерации ответа для режима Оракула.
    Здесь может быть вызов ChatGPT API с ролевой моделью Оракула.
    В данном примере возвращается заглушка.
    """
    return f"Ответ Оракула на вопрос: {question}"

def check_and_reset_limits(user: dict) -> None:
    """
    Проверяем и, при необходимости, сбрасываем лимиты:
      - Для платного режима (если подписка активна) сбрасываем лимит, если время истекло.
      - Для бесплатного режима сбрасываем лимит, если прошел период в 30 дней.
    """
    now = datetime.now()
    if user.get("premium") and user.get("premium_expires_at") and now < user["premium_expires_at"]:
        if user.get("premium_reset_at") is None or now > user["premium_reset_at"]:
            user["premium_answers_left"] = PREMIUM_QUESTIONS_PER_DAY
            user["premium_reset_at"] = now + timedelta(hours=PREMIUM_PERIOD_HOURS)
    else:
        if user.get("free_reset_at") is None or now > user["free_reset_at"]:
            user["free_answers_left"] = FREE_QUESTIONS_PER_PERIOD
            user["free_reset_at"] = now + timedelta(days=FREE_PERIOD_DAYS)

async def handle_oracle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик режима Оракула с проверкой лимитов.
    Если лимит бесплатного режима исчерпан, предлагает оформить подписку.
    Если лимит платного режима исчерпан, сообщает о времени до обновления.
    """
    user_id = update.effective_user.id
    question = update.message.text.strip()

    user = database.get_user_by_telegram_id(user_id)
    if not user:
        # Если пользователя нет в БД, создаём новую запись
        user = {
            "telegram_id": user_id,
            "premium": False,
            "premium_expires_at": None,
            "premium_answers_left": 0,
            "premium_reset_at": None,
            "free_answers_left": FREE_QUESTIONS_PER_PERIOD,
            "free_reset_at": datetime.now() + timedelta(days=FREE_PERIOD_DAYS),
            "username": update.effective_user.username
        }
        database.create_user(user)

    now = datetime.now()
    premium_active = user.get("premium") and user.get("premium_expires_at") and now < user["premium_expires_at"]

    check_and_reset_limits(user)

    if premium_active:
        if user.get("premium_answers_left", 0) > 0:
            user["premium_answers_left"] -= 1
            database.update_user(user)
            answer = generate_oracle_answer(question)
            await update.message.reply_text(answer)
        else:
            time_left = user["premium_reset_at"] - now
            hours_left = time_left.seconds // 3600
            minutes_left = (time_left.seconds % 3600) // 60
            await update.message.reply_text(
                f"Лимит платных вопросов исчерпан. Следующее обновление через {hours_left} ч. {minutes_left} мин."
            )
    else:
        if user.get("free_answers_left", 0) > 0:
            user["free_answers_left"] -= 1
            database.update_user(user)
            answer = generate_oracle_answer(question)
            await update.message.reply_text(answer)
        else:
            keyboard = [
                [InlineKeyboardButton("Оформить подписку", callback_data="subscribe")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Вы исчерпали бесплатный лимит (5 вопросов на 30 дней). Оформите подписку для получения 20 вопросов в сутки.",
                reply_markup=reply_markup
            )

async def subscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик нажатия кнопки для оформления подписки.
    Здесь можно интегрировать платёжную систему; в данном примере подписка активируется сразу.
    """
    query = update.callback_query
    user_id = query.from_user.id
    user = database.get_user_by_telegram_id(user_id)
    now = datetime.now()
    user["premium"] = True
    user["premium_expires_at"] = now + timedelta(days=30)
    user["premium_answers_left"] = PREMIUM_QUESTIONS_PER_DAY
    user["premium_reset_at"] = now + timedelta(hours=PREMIUM_PERIOD_HOURS)
    database.update_user(user)
    await query.answer("Подписка оформлена!")
    await query.edit_message_text("Подписка успешно оформлена! Теперь у вас 20 вопросов в сутки для режима Оракула.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(config["messages"]["start"])

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("oracle", handle_oracle))
    # Если у вас есть режим Магического шара, оставляем его без изменений:
    # app.add_handler(CommandHandler("magicball", handle_magicball))
    app.add_handler(CallbackQueryHandler(subscribe_callback, pattern="^subscribe$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_oracle))
    
    app.run_polling()

if __name__ == "__main__":
    main()
