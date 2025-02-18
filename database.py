import logging
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Подключение к БД
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
        logging.info("Подключение к БД установлено.")
        return conn
    except psycopg2.Error as e:
        logging.error(f"Ошибка подключения к БД: {e}")
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
                    "INSERT INTO users (telegram_id, username, created_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING;",
                    (telegram_id, username, datetime.utcnow()),
                )
                logging.info(f"Добавлен пользователь {telegram_id} ({username}) в БД.")
    except psycopg2.Error as e:
        logging.error(f"Ошибка при добавлении пользователя {telegram_id}: {e}")
    finally:
        conn.close()

# Получение пользователя
def get_user(telegram_id):
    conn = get_db_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE telegram_id = %s;", (telegram_id,))
            user = cur.fetchone()
            logging.info(f"Запрос информации о пользователе {telegram_id}: {user}")
            return user
    except psycopg2.Error as e:
        logging.error(f"Ошибка при получении пользователя {telegram_id}: {e}")
        return None
    finally:
        conn.close()

# Обновление режима подписки
def update_user_subscription(telegram_id, premium_status):
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET premium = %s WHERE telegram_id = %s;",
                    (premium_status, telegram_id),
                )
                logging.info(f"Пользователь {telegram_id} теперь {'премиум' if premium_status else 'обычный'}.")
    except psycopg2.Error as e:
        logging.error(f"Ошибка при обновлении подписки пользователя {telegram_id}: {e}")
    finally:
        conn.close()


# Получаем данные из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL")

# Функция для соединения с базой
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)

# Функция для записи сообщений
def log_message(user_id, message_text, response_text, mode):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO message_logs (user_id, message_text, response_text, mode) VALUES (%s, %s, %s, %s)",
            (user_id, message_text, response_text, mode)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Ошибка при сохранении сообщения в базу: {e}")
