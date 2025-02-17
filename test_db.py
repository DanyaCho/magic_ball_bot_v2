from database import add_user, get_user, update_user_subscription

# Добавляем тестового пользователя
add_user(123456789, "TestUser")

# Получаем информацию о пользователе
print(get_user(123456789))

# Делаем пользователя премиумом
update_user_subscription(123456789, True)

# Проверяем обновление
print(get_user(123456789))
