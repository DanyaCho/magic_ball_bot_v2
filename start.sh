#!/bin/bash

# Активация виртуального окружения
source venv/bin/activate

# Запуск сервера Hypercorn
hypercorn bot:app --bind 0.0.0.0:${PORT}