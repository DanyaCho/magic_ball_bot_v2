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
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (telegram_id, username, created_at) 
                    VALUES (%s, %s, %s) 
                    ON CONFLICT (telegram_id) DO NOTHING;
                    """,
                    (telegram_id, username, datetime.utcnow()),
                )
                logger.info(f"Добавлен пользователь {telegram_id} ({username}) в БД.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при добавлении пользователя {telegram_id}: {e}")
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
            logger.info(f"Запрос информации о пользователе {telegram_id}: {user}")
            return user
    except psycopg2.Error as e:
        logger.error(f"Ошибка при получении пользователя {telegram_id}: {e}")
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
                logger.info(f"Пользователь {telegram_id} теперь {'премиум' if premium_status else 'обычный'}.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при обновлении подписки пользователя {telegram_id}: {e}")
    finally:
        conn.close()

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


def unlock_soul(user_id, soul_name):
    """Добавляет душу в список доступных для пользователя."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Проверяем, есть ли уже такая душа у пользователя
    cur.execute("SELECT * FROM user_souls WHERE user_id = %s AND soul_name = %s", (user_id, soul_name))
    if cur.fetchone():
        cur.close()
        conn.close()
        return False  # Душа уже разблокирована

    # Добавляем новую душу
    cur.execute(
        "INSERT INTO user_souls (user_id, soul_name, unlocked_at) VALUES (%s, %s, %s)",
        (user_id, soul_name, datetime.now()),
    )
    conn.commit()
    cur.close()
    conn.close()
    return True  # Душа успешно добавлена

def get_unlocked_souls(user_id):
    """Возвращает список разблокированных душ пользователя."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("SELECT soul_name FROM user_souls WHERE user_id = %s", (user_id,))
    souls = [row[0] for row in cur.fetchall()]

    cur.close()
    conn.close()
    return souls  # Возвращает список имен душ
