import psycopg2
from datetime import datetime, timedelta, date
import logging
import os
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("Подключение к БД установлено.")
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        raise

def add_user(telegram_id, username):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (telegram_id, username, premium, oracle_requests, last_oracle_request) "
                    "VALUES (%s, %s, FALSE, 3, NULL) ON CONFLICT (telegram_id) DO NOTHING",
                    (telegram_id, username)
                )
    except Exception as e:
        logger.error(f"Ошибка при добавлении пользователя: {e}")
    finally:
        conn.close()

def get_user(telegram_id):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT telegram_id, username, premium, premium_expires_at, oracle_requests, last_oracle_request "
                    "FROM users WHERE telegram_id = %s",
                    (telegram_id,)
                )
                user = cur.fetchone()
                if user:
                    return {
                        "telegram_id": user[0],
                        "username": user[1],
                        "premium": user[2],
                        "premium_expires_at": user[3],
                        "oracle_requests": user[4],
                        "last_oracle_request": user[5]
                    }
                return None
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя: {e}")
        return None
    finally:
        conn.close()

def activate_premium(telegram_id):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Проверяем, есть ли пользователь
                cur.execute("SELECT premium, premium_expires_at FROM users WHERE telegram_id = %s", (telegram_id,))
                user = cur.fetchone()
                if not user:
                    logger.error(f"Пользователь {telegram_id} не найден при активации премиум-подписки.")
                    return False

                # Устанавливаем премиум на 30 дней (только дата)
                new_expiry = (datetime.utcnow() + timedelta(days=30)).date()
                if user[0] and user[1]:  # user[0] - premium, user[1] - premium_expires_at
                    # Если подписка уже активна, добавляем 30 дней к текущей дате окончания
                    current_expiry = user[1]
                    if isinstance(current_expiry, datetime):
                        current_expiry = current_expiry.date()
                    if current_expiry > datetime.utcnow().date():
                        new_expiry = (current_expiry + timedelta(days=30))
                        logger.info(f"Подписка уже активна, продлеваем до {new_expiry}")
                    else:
                        logger.info(f"Подписка истекла, устанавливаем новую дату: {new_expiry}")
                else:
                    logger.info(f"Новая подписка, устанавливаем дату: {new_expiry}")

                cur.execute(
                    "UPDATE users SET premium = TRUE, premium_expires_at = %s WHERE telegram_id = %s",
                    (new_expiry, telegram_id)
                )
                logger.info(f"Премиум-подписка активирована для {telegram_id} до {new_expiry}")
                return True
    except Exception as e:
        logger.error(f"Ошибка при активации премиум-подписки: {e}")
        return False
    finally:
        conn.close()

def log_payment(telegram_id, amount, currency, charge_id):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO payments (telegram_id, amount, currency, charge_id, payment_date) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (telegram_id, amount, currency, charge_id, datetime.utcnow())
                )
    except Exception as e:
        logger.error(f"Ошибка при логировании платежа: {e}")
    finally:
        conn.close()

def check_and_decrement_oracle_limit(telegram_id, username, config):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT premium, premium_expires_at, oracle_requests, last_oracle_request "
                    "FROM users WHERE telegram_id = %s",
                    (telegram_id,)
                )
                user = cur.fetchone()
                if not user:
                    cur.execute(
                        "INSERT INTO users (telegram_id, username, premium, oracle_requests, last_oracle_request) "
                        "VALUES (%s, %s, FALSE, 3, NULL)",
                        (telegram_id, username)
                    )
                    return True, None

                premium, premium_expires_at, oracle_requests, last_oracle_request = user

                # Проверяем премиум
                current_date = datetime.utcnow().date()
                if premium and premium_expires_at:
                    expires_at_date = premium_expires_at.date() if isinstance(premium_expires_at, datetime) else premium_expires_at
                    if expires_at_date < current_date:
                        cur.execute(
                            "UPDATE users SET premium = FALSE, premium_expires_at = NULL WHERE telegram_id = %s",
                            (telegram_id,)
                        )
                        premium = False

                if premium:
                    return True, None

                # Проверяем лимит запросов
                if last_oracle_request:
                    last_request_date = last_oracle_request.date() if isinstance(last_oracle_request, datetime) else last_oracle_request
                    if last_request_date < current_date:
                        oracle_requests = config["oracle"]["daily_limit"]

                if oracle_requests <= 0:
                    return False, config["messages"]["oracle_limit_exceeded"]

                # Уменьшаем лимит и обновляем дату последнего запроса
                cur.execute(
                    "UPDATE users SET oracle_requests = %s, last_oracle_request = %s WHERE telegram_id = %s",
                    (oracle_requests - 1, datetime.utcnow(), telegram_id)
                )
                return True, None
    except Exception as e:
        logger.error(f"Ошибка при проверке лимита Оракула: {e}")
        return False, "Произошла ошибка. Попробуйте позже."
    finally:
        conn.close()

def log_message(telegram_id, user_message, bot_response, mode):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO messages (telegram_id, user_message, bot_response, mode, timestamp) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (telegram_id, user_message, bot_response, mode, datetime.utcnow())
                )
    except Exception as e:
        logger.error(f"Ошибка при логировании сообщения: {e}")
    finally:
        conn.close()
