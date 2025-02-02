from database import SessionLocal, User, init_db

# Создаем таблицы в БД
init_db()

# Создаем сессию
db = SessionLocal()

# Добавляем тестового пользователя
test_user = User(telegram_id=123456789, username="TestUser", premium=False, free_answers_left=3)
db.add(test_user)
db.commit()

# Проверяем, что пользователь добавлен
user = db.query(User).filter(User.telegram_id == 123456789).first()
if user:
    print(f"Пользователь найден: {user.username}, подписка: {user.premium}, бесплатных ответов: {user.free_answers_left}")
else:
    print("Ошибка: Пользователь не найден.")

db.close()
