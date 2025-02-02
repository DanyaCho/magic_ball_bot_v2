from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Получаем URL базы данных из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL")

# Создаем движок базы данных
engine = create_engine(DATABASE_URL)

# Создаем сессию
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
Base = declarative_base()

# Таблица пользователей
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    premium = Column(Boolean, default=False)  # Есть ли подписка
    free_answers_left = Column(Integer, default=3)  # Остаток бесплатных ответов
    created_at = Column(DateTime, default="now()")

# Таблица скрытых режимов
class HiddenMode(Base):
    __tablename__ = "hidden_modes"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, nullable=False)
    mode_name = Column(String, nullable=False)
    unlocked = Column(Boolean, default=False)  # Открыт ли режим

# Создаем таблицы в базе данных
def get_user(db, telegram_id: int):
    return db.query(User).filter(User.telegram_id == telegram_id).first()
def init_db():
    Base.metadata.create_all(bind=engine)
