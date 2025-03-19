import random
import json
from datetime import datetime
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import openai
from dotenv import load_dotenv
import os
import logging
from openai.error import RateLimitError, AuthenticationError
import asyncio
from telegram.error import Conflict

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not BOT_TOKEN or not OPENAI_API_KEY:
    logger.error("Отсутствует BOT_TOKEN или OPENAI_API_KEY в переменных окружения.")
    exit(1)
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
async def generate_oracle_response(question, context):
    soul_name = context.user_data.get("soul", "oracle")
    soul_description = config["characters"][soul_name]["description"]
    logger.info(f"Выбранная душа: {soul_name}")
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": soul_description},
                      {"role": "user", "content": question}]
        )["choices"][0]["message"]["content"].strip()
        return response
    except RateLimitError:
        logger.error("Превышен лимит запросов к OpenAI.")
        return "Превышен лимит запросов. Попробуй позже."
    except AuthenticationError:
        logger.error("Неверный ключ OpenAI.")
        return "Ошибка авторизации. Обратитесь к администратору."
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

    keyboard = [
        [InlineKeyboardButton("Купить Премиум (30 дней)", callback_data="buy_premium")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Премиум-подписка даёт 20 ответов Оракула в день на 30 дней!\nБесплатный лимит: 10 ответов в месяц.",
        reply_markup=reply_markup
    )

# Обработка callback для покупки премиум
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
    logger.info(f"Текущий режим: {context.user_data.get('mode', 'oracle')}, Сообщение: {user_message}")

    # Обработка скрытого режима
    if user_message.lower() == config["hidden_mode_trigger"]:
        context.user_data["mode"] = "hidden"
        await update.message.reply_text(config["messages"]["hidden_mode_activated"])
        return
    elif context.user_data.get("mode") == "hidden":
        response = random.choice(config["hidden_mode_responses"])
        await update.message.reply_text(response)
        return

    # Определяем текущий режим
    mode = context.user_data.get("mode", "oracle")
    
    # Генерируем ответ
    if mode == "magic_ball":
        response = await generate_magic_ball_response(user_message, user_id, context)
    else:
        # Проверка лимитов для Оракула
        can_respond, error_message = database.check_and_decrement_oracle_limit(user_id)
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
            BotCommand("premium", "Купить премиум-подписку")
        ]
        await application.bot.set_my_commands(commands)
        logging.info("Команды успешно установлены.")
    except Exception as e:
        logging.error(f"Ошибка при установке команд: {e}")

# Основной запуск бота
async def run_bot():
    logger.info("Запуск бота...")
    application = None
    is_running = False
    while True:
        try:
            application = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()
            
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("oracle", oracle))
            application.add_handler(CommandHandler("magicball", magicball))
            application.add_handler(CommandHandler("premium", premium))
            application.add_handler(CallbackQueryHandler(handle_premium_callback, pattern='^buy_premium$'))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            await application.initialize()
            await application.start()
            is_running = True
            await application.run_polling(allowed_updates=Update.ALL_TYPES)
            break  # Выходим из цикла, если всё работает
        except Conflict as e:
            logger.error(f"Конфликт подключения: {e}. Переподключение через 5 секунд...")
            if application and is_running:
                await application.stop()
                await application.shutdown()
                is_running = False
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Ошибка в основном цикле бота: {e}")
            if application and is_running:
                await application.stop()
                await application.shutdown()
                is_running = False
            await asyncio.sleep(5)
        finally:
            if application and is_running:
                try:
                    await application.stop()
                    await application.shutdown()
                except Exception as e:
                    logger.error(f"Ошибка при завершении application: {e}")

def main():
    # Создаём цикл событий вручную
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")
    finally:
        # Убедимся, что все задачи завершены
        pending = asyncio.all_tasks(loop=loop)
        for task in pending:
            task.cancel()
        loop.stop()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

if __name__ == "__main__":
    main()
