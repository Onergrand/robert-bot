#!/bin/bash
# Скрипт для автоматического развертывания бота на сервере

set -e  # Остановка при ошибке

echo "=== Развертывание ParserTaxi Bot ==="

# Проверка Python
if ! command -v python3.11 &> /dev/null; then
    echo "Ошибка: Python 3.11 не найден. Установите Python 3.11 или выше."
    exit 1
fi

# Проверка PostgreSQL
if ! command -v psql &> /dev/null; then
    echo "Ошибка: PostgreSQL не найден. Установите PostgreSQL."
    exit 1
fi

# Создание виртуального окружения
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    python3.11 -m venv venv
fi

# Активация виртуального окружения
echo "Активация виртуального окружения..."
source venv/bin/activate

# Установка зависимостей
echo "Установка зависимостей..."
pip install --upgrade pip
pip install -r requirements.txt

# Проверка наличия .env файла
if [ ! -f ".env" ]; then
    echo "ВНИМАНИЕ: Файл .env не найден!"
    echo "Скопируйте env.example.txt в .env и заполните переменные окружения."
    if [ -f "env.example.txt" ]; then
        cp env.example.txt .env
        echo "Создан файл .env из env.example.txt. Отредактируйте его перед запуском!"
    elif [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Создан файл .env из .env.example. Отредактируйте его перед запуском!"
    fi
    exit 1
fi

# Проверка подключения к БД
echo "Проверка подключения к базе данных..."
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
db_url = os.getenv('DATABASE_URL')
if not db_url:
    print('Ошибка: DATABASE_URL не установлен в .env')
    exit(1)
print('DATABASE_URL найден')
"

# Инициализация БД (если нужно)
if [ -f "schema.sql" ]; then
    read -p "Выполнить SQL скрипт schema.sql для создания таблиц? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Выполнение schema.sql..."
        # Извлекаем данные из DATABASE_URL
        DB_URL=$(grep DATABASE_URL .env | cut -d '=' -f2-)
        # Парсим URL (упрощенная версия)
        # Формат: postgresql+asyncpg://user:pass@host:port/db
        # Для psql нужен формат: postgresql://user:pass@host:port/db
        PSQL_URL=$(echo $DB_URL | sed 's/postgresql+asyncpg/postgresql/g')
        psql "$PSQL_URL" -f schema.sql || {
            echo "Ошибка при выполнении schema.sql. Выполните вручную:"
            echo "psql -U user -d database -f schema.sql"
        }
    fi
fi

echo ""
echo "=== Развертывание завершено! ==="
echo ""
echo "Следующие шаги:"
echo "1. Убедитесь, что .env файл заполнен корректно"
echo "2. Проверьте, что таблицы БД созданы (выполните schema.sql если нужно)"
echo "3. Запустите бота:"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
echo "Или используйте systemd для автозапуска:"
echo "   sudo cp parsertaxi-bot.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable parsertaxi-bot"
echo "   sudo systemctl start parsertaxi-bot"

