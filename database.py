import logging
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
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
    """Добавляет нового пользователя в БД, если его там нет"""
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (telegram_id, username, premium, free_answers_left, created_at) 
                    VALUES (%s, %s, %s, %s, %s) 
                    ON CONFLICT (telegram_id) DO NOTHING;
                    """,
                    (telegram_id, username, False, 5, datetime.utcnow()),
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
            "SELECT id, telegram_id, username, premium, free_answers_left, created_at FROM users WHERE telegram_id = %s",
            (telegram_id,),
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

# Уменьшение количества бесплатных ответов у пользователя
def decrease_free_answers(telegram_id):
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users 
                    SET free_answers_left = free_answers_left - 1 
                    WHERE telegram_id = %s AND free_answers_left > 0
                    RETURNING free_answers_left;
                    """,
                    (telegram_id,),
                )
                updated_value = cur.fetchone()
                if updated_value:
                    logger.info(f"Бесплатные ответы уменьшены для пользователя {telegram_id}. Осталось: {updated_value[0]}")
                else:
                    logger.warning(f"Не удалось уменьшить free_answers_left для {telegram_id} (возможно, уже 0).")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при уменьшении количества бесплатных ответов {telegram_id}: {e}")
    finally:
        conn.close()
