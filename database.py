import logging
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Подключение к БД
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
        logger.info("Подключение к БД установлено.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None

# Добавление пользователя
def add_user(telegram_id, username):
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (telegram_id, username, premium, oracle_monthly_answers_left, oracle_daily_answers_left, created_at, free_reset_at, premium_reset_at, premium_expires_at) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) 
                    ON CONFLICT (telegram_id) DO NOTHING;
                    """,
                    (telegram_id, username, False, 10, 0, datetime.utcnow(), datetime.utcnow(), datetime.utcnow(), None),
                )
                logger.info(f"Добавлен пользователь {telegram_id} ({username}) в БД.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при добавлении пользователя {telegram_id}: {e}")
    finally:
        conn.close()

def get_user(telegram_id):
    """Получает информацию о пользователе по его Telegram ID."""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, telegram_id, username, premium, oracle_monthly_answers_left, oracle_daily_answers_left, created_at, free_reset_at, premium_reset_at, premium_expires_at FROM users WHERE telegram_id = %s",
            (telegram_id,)
        )
        return cur.fetchone()
    except psycopg2.Error as e:
        logger.error(f"Ошибка при получении данных пользователя {telegram_id}: {e}")
        return None
    finally:
        conn.close()

# Получение разблокированных душ пользователя
def get_user_souls(user_id):
    """Получает список разблокированных душ пользователя."""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT soul_name FROM user_souls WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s)", (user_id,))
        souls = [row[0] for row in cur.fetchall()]
        cur.close()
        return souls
    except Exception as e:
        logger.error(f"Ошибка получения душ для {user_id}: {e}")
        return []
    finally:
        conn.close()

# Разблокировка души
def unlock_soul(user_id, soul_name):
    """Разблокирует душу для пользователя, если её ещё нет."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
        user_row = cur.fetchone()

        if user_row:
            db_user_id = user_row[0]

            # Проверяем, есть ли уже эта душа у пользователя
            cur.execute("SELECT * FROM user_souls WHERE user_id = %s AND soul_name = %s", (db_user_id, soul_name))
            if cur.fetchone():
                conn.close()
                return False  # Душа уже открыта

            # Добавляем новую душу
            cur.execute("INSERT INTO user_souls (user_id, soul_name, unlocked_at) VALUES (%s, %s, %s)",
                        (db_user_id, soul_name, datetime.utcnow()))
            conn.commit()
            conn.close()
            return True  # Душа разблокирована
    except Exception as e:
        logger.error(f"Ошибка разблокировки души {soul_name} для {user_id}: {e}")
        return False

# Функция для записи сообщений в лог
def log_message(telegram_id, message_text, response_text, mode):
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO message_logs (telegram_id, message_text, response_text, mode) 
                    VALUES (%s, %s, %s, %s);
                    """,
                    (telegram_id, message_text, response_text, mode),
                )
                logger.info(f"Лог сообщения добавлен для пользователя {telegram_id}.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при сохранении сообщения в базу для пользователя {telegram_id}: {e}")
    finally:
        conn.close()

# Функция для записи платежей в лог
def log_payment(telegram_id, amount, currency, charge_id):
    conn = get_db_connection()
    if not conn:
        logger.error("Не удалось подключиться к базе данных для записи платежа.")
        return

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO payment_logs (telegram_id, amount, currency, charge_id, created_at) 
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (telegram_id, amount, currency, charge_id, datetime.utcnow()),
                )
                logger.info(f"Лог платежа добавлен для пользователя {telegram_id}.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при сохранении платежа для {telegram_id}: {e}")
    finally:
        conn.close()

# Проверка и обновление лимитов
def reset_limits_if_needed(telegram_id):
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT premium, oracle_monthly_answers_left, oracle_daily_answers_left, free_reset_at, premium_reset_at, premium_expires_at "
                    "FROM users WHERE telegram_id = %s",
                    (telegram_id,)
                )
                user = cur.fetchone()
                if not user:
                    return False

                premium, monthly_left, daily_left, free_reset, premium_reset, expires_at = user
                today = datetime.utcnow().date()

                # Сброс месячного лимита
                if not free_reset or free_reset.month != today.month or free_reset.year != today.year:
                    monthly_left = 10
                    cur.execute(
                        "UPDATE users SET oracle_monthly_answers_left = %s, free_reset_at = %s WHERE telegram_id = %s",
                        (monthly_left, today, telegram_id)
                    )

                # Сброс дневного лимита для премиум
                if premium and (not premium_reset or premium_reset.date() != today):
                    # Приводим expires_at к datetime.date, если это datetime.datetime
                    expires_at_date = expires_at.date() if isinstance(expires_at, datetime) else expires_at
                    daily_left = 20 if (not expires_at_date or expires_at_date > today) else 0
                    cur.execute(
                        "UPDATE users SET oracle_daily_answers_left = %s, premium_reset_at = %s WHERE telegram_id = %s",
                        (daily_left, today, telegram_id)
                    )

                return True
    except psycopg2.Error as e:
        logger.error(f"Ошибка при сбросе лимитов для {telegram_id}: {e}")
        return False
    finally:
        conn.close()

# Проверка лимитов и уменьшение счетчиков
def check_and_decrement_oracle_limit(telegram_id, username, config):
    conn = get_db_connection()
    if not conn:
        return False, "Ошибка базы данных."

    try:
        with conn:
            with conn.cursor() as cur:
                reset_limits_if_needed(telegram_id)
                cur.execute(
                    "SELECT premium, oracle_monthly_answers_left, oracle_daily_answers_left, premium_expires_at "
                    "FROM users WHERE telegram_id = %s",
                    (telegram_id,)
                )
                user = cur.fetchone()
                if not user:
                    add_user(telegram_id, username or "unknown")
                    cur.execute(
                        "SELECT premium, oracle_monthly_answers_left, oracle_daily_answers_left, premium_expires_at "
                        "FROM users WHERE telegram_id = %s",
                        (telegram_id,)
                    )
                    user = cur.fetchone()

                premium, monthly_left, daily_left, expires_at = user
                today = datetime.utcnow().date()

                if not premium and monthly_left <= 0:
                    return False, config["messages"]["limit_exceeded_free"]
                
                # Приводим expires_at к datetime.date, если это datetime.datetime
                expires_at_date = expires_at.date() if isinstance(expires_at, datetime) else expires_at
                if premium and (expires_at_date and expires_at_date < today):
                    return False, "Ваша премиум-подписка истекла."
                elif premium and daily_left <= 0:
                    return False, config["messages"]["limit_exceeded_premium"]

                # Уменьшаем лимиты в зависимости от статуса подписки
                if premium:
                    # Для премиум-пользователей уменьшаем только дневной лимит
                    cur.execute(
                        "UPDATE users SET oracle_daily_answers_left = oracle_daily_answers_left - 1 WHERE telegram_id = %s",
                        (telegram_id,)
                    )
                else:
                    # Для бесплатных пользователей уменьшаем только месячный лимит
                    cur.execute(
                        "UPDATE users SET oracle_monthly_answers_left = oracle_monthly_answers_left - 1 WHERE telegram_id = %s",
                        (telegram_id,)
                    )
                return True, ""
    except psycopg2.Error as e:
        logger.error(f"Ошибка при проверке лимита для {telegram_id}: {e}")
        return False, "Ошибка базы данных."
    finally:
        conn.close()

# Активация премиум с указанием срока
def activate_premium(telegram_id):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Проверяем, есть ли пользователь
                cur.execute("SELECT premium, premium_expires_at FROM users WHERE telegram_id = %s", (telegram_id,))
                user = cur.fetchone()
                if not user:
                    return False

                # Устанавливаем премиум на 30 дней (только дата)
                new_expiry = (datetime.utcnow() + timedelta(days=30)).date()
                if user["premium"] and user["premium_expires_at"]:
                    # Если подписка уже активна, добавляем 30 дней к текущей дате окончания
                    current_expiry = user["premium_expires_at"]
                    if isinstance(current_expiry, datetime):
                        current_expiry = current_expiry.date()
                    if current_expiry > datetime.utcnow().date():
                        new_expiry = (current_expiry + timedelta(days=30))

                cur.execute(
                    "UPDATE users SET premium = TRUE, premium_expires_at = %s WHERE telegram_id = %s",
                    (new_expiry, telegram_id)
                )
                return True
    except Exception as e:
        logger.error(f"Ошибка при активации премиум-подписки: {e}")
        return False
    finally:
        conn.close()
