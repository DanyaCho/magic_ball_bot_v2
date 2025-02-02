import os
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Подключение к базе данных
DB_PARAMS = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
}

def get_db_connection():
    """Создает подключение к базе данных"""
    return psycopg2.connect(**DB_PARAMS, cursor_factory=DictCursor)

def create_tables():
    """Создает таблицы, если их нет"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username TEXT,
                    premium BOOLEAN DEFAULT FALSE,
                    free_answers_remaining INT DEFAULT 3,
                    discovered_modes TEXT[] DEFAULT '{}'
                );
            """)
            conn.commit()

def get_user(telegram_id):
    """Получает данные о пользователе"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE telegram_id = %s;", (telegram_id,))
            return cur.fetchone()

def add_user(telegram_id, username):
    """Добавляет нового пользователя"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (telegram_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                (telegram_id, username)
            )
            conn.commit()

def update_user_subscription(telegram_id, is_premium):
    """Обновляет подписку пользователя"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET premium = %s WHERE telegram_id = %s;",
                (is_premium, telegram_id)
            )
            conn.commit()

def decrease_free_answers(telegram_id):
    """Уменьшает количество бесплатных ответов"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET free_answers_remaining = free_answers_remaining - 1 WHERE telegram_id = %s AND free_answers_remaining > 0 RETURNING free_answers_remaining;",
                (telegram_id,)
            )
            result = cur.fetchone()
            return result["free_answers_remaining"] if result else 0

def add_discovered_mode(telegram_id, mode):
    """Добавляет найденный скрытый режим"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET discovered_modes = array_append(discovered_modes, %s) WHERE telegram_id = %s;",
                (mode, telegram_id)
            )
            conn.commit()
