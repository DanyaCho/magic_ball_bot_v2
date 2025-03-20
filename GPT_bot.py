import random
import json
from datetime import datetime
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, PreCheckoutQueryHandler
import openai
from dotenv import load_dotenv
import os
import logging
import database
import time
from telegram.error import Conflict

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not BOT_TOKEN or not OPENAI_API_KEY:
    logger.error("Отсутствует BOT_TOKEN или OPENAI_API_KEY в переменных окружения.")
    exit(1)
openai.api_key = OPENAI_API_KEY

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

# Команда /paysupport
async def paysupport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пожалуйста, напишите причину запроса на возврат. Мы рассмотрим ваш запрос в ближайшее время.")
    logger.info(f"Пользователь {update.message.from_user.id} запросил поддержку по платежам.")

# Команда /checkstars (только для владельца бота)
async def check_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    # Проверяем, что это владелец бота (замени на свой Telegram ID)
    if user_id != 5028281352:
        await update.message.reply_text("Эта команда доступна только владельцу бота.")
        return

    try:
        # Запрашиваем статус звёзд через Telegram API
        stars_status = await context.bot.get_stars_status(peer={"_": "inputPeerSelf"})
        balance = stars_status.balance
        available_for_withdrawal = stars_status.available_for_withdrawal
        await update.message.reply_text(
            f"Текущий баланс звёзд: {balance} XTR\n"
            f"Доступно для вывода: {available_for_withdrawal} XTR\n"
            f"Для вывода нужно минимум 1000 XTR и 21 день ожидания."
        )
    except Exception as e:
        logger.error(f"Ошибка при получении баланса звёзд: {e}")
        await update.message.reply_text("Не удалось проверить баланс звёзд.")

# Генерация ответа для Магического Шара
async def generate_magic_ball_response(question, telegram_id, context):
    chosen_tone = random.choice(["negative", "positive", "neutral"])
    response = random.choice(config["magic_ball_responses"].get(chosen_tone, []))
    logger.info(f"Ответ Магического Шара для {telegram_id}: {response}")
    return response

# Генерация ответа для Оракула
async def generate_oracle_response(question, context):
    logger.info("Генерация ответа Оракула...")
    soul_name = context.user_data.get("soul", "oracle")
    logger.info(f"Выбранная душа: {soul_name}")
    soul_description = config["characters"][soul_name]["description"]
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": soul_description},
                      {"role": "user", "content": question}]
        )["choices"][0]["message"]["content"].strip()
        logger.info(f"Ответ от OpenAI: {response}")
        return response
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {e}")
        return config["messages"]["oracle_error"]

# Команда /premium
async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = database.get_user(user_id)
    if not user:
        database.add_user(user_id, update.message.from_user.username or "unknown")
        user = database.get_user(user_id)

    if user["premium"] and user["premium_expires_at"] and user["premium_expires_at"] > datetime.utcnow().date():
        await update.message.reply_text("У вас уже есть премиум-подписка!")
        return

    # Отправляем инвойс для оплаты премиум-подписки в Telegram Stars
    await update.message.reply_invoice(
        title=config["payment"]["premium_label"],
        description=config["payment"]["premium_description"],
        payload="premium_subscription_30_days",  # Уникальный идентификатор покупки
        provider_token=config["payment"]["provider_token"],  # Пустой для XTR
        currency=config["payment"]["currency"],  # XTR для Telegram Stars
        prices=[LabeledPrice(config["payment"]["premium_label"], config["payment"]["premium_price"])],
        need_email=False,
        need_phone_number=False,
        need_shipping_address=False,
        is_flexible=False
    )

# Обработка предпроверки платежа
async def pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    # Проверяем payload
    if query.invoice_payload != "premium_subscription_30_days":
        await query.answer(ok=False, error_message="Неверный payload.")
        logger.error(f"Ошибка предпроверки для пользователя {query.from_user.id}: Неверный payload")
        return
    # Подтверждаем предпроверку
    await query.answer(ok=True)

# Обработка успешного платежа
async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        payment = update.message.successful_payment
        logger.info(f"Успешный платёж: user_id={user_id}, amount={payment.total_amount}, currency={payment.currency}, charge_id={payment.telegram_payment_charge_id}")

        # Сохраняем информацию о платеже в базе данных
        database.log_payment(user_id, payment.total_amount, payment.currency, payment.telegram_payment_charge_id)

        # Активируем премиум-подписку
        if database.activate_premium(user_id):
            await update.message.reply_text(config["messages"]["premium_success"])
        else:
            await update.message.reply_text("Ошибка активации премиум-подписки. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Ошибка при обработке платежа: {e}")
        await update.message.reply_text("Произошла ошибка при обработке платежа. Попробуйте позже.")

# Обработка callback для покупки премиум (оставляем для совместимости)
async def handle_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if database.activate_premium(user_id):
        await query.edit_message_text("Премиум-подписка активирована на 30 дней!")
    else:
        await query.edit_message_text("Ошибка активации. Попробуйте позже.")

# Обработка входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.strip()
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    logger.info(f"Текущий режим: {context.user_data.get('mode', 'oracle')}, Сообщение: {user_message}")

    # Определяем текущий режим
    mode = context.user_data.get("mode", "oracle")
    
    # Генерируем ответ
    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message, user_id, context)
    else:
        # Проверка лимитов для Оракула
        can_respond, error_message = database.check_and_decrement_oracle_limit(user_id, username, config)
        logger.info(f"Можно отвечать: {can_respond}, Сообщение об ошибке: {error_message}")
        if not can_respond:
            await update.message.reply_text(error_message)
            return
        response = await generate_oracle_response(user_message, context)

    database.log_message(user_id, user_message, response, mode)
    await update.message.reply_text(response)

# Настройка команд
async def set_commands(application):
    try:
        commands = [
            BotCommand("start", "Начать работу"),
            BotCommand("oracle", "Переключиться в режим Оракула"),
            BotCommand("magicball", "Переключиться в режим Магического шара"),
            BotCommand("premium", "Купить премиум-подписку"),
            BotCommand("paysupport", "Запросить возврат платежа"),
            BotCommand("checkstars", "Проверить баланс звёзд (для владельца)")
        ]
        await application.bot.set_my_commands(commands)
        logger.info("Команды успешно установлены.")
    except Exception as e:
        logger.error(f"Ошибка при установке команд: {e}")

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

# Основной запуск бота
def main():
    while True:
        application = None
        try:
            logger.info("Запуск бота...")
            application = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()
            
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("oracle", oracle))
            application.add_handler(CommandHandler("magicball", magicball))
            application.add_handler(CommandHandler("premium", premium))
            application.add_handler(CommandHandler("paysupport", paysupport))
            application.add_handler(CommandHandler("checkstars", check_stars))
            application.add_handler(CallbackQueryHandler(handle_premium_callback, pattern='^buy_premium$'))
            application.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
            application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            application.add_error_handler(error_handler)
            
            logger.info("Начинаем polling...")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Conflict as e:
            logger.error(f"Конфликт: {e}. Перезапуск через 5 секунд...")
            if application:
                logger.info("Останавливаем Application...")
                application.stop()
                application.shutdown()
            time.sleep(5)  # Ждём 5 секунд перед перезапуском
        except Exception as e:
            logger.error(f"Ошибка в основном цикле бота: {e}")
            if application:
                logger.info("Останавливаем Application...")
                application.stop()
                application.shutdown()
            break
        finally:
            if application:
                logger.info("Завершаем Application...")
                application.stop()
                application.shutdown()

if __name__ == "__main__":
    main()
