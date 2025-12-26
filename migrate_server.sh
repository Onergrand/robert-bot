#!/bin/bash
# Скрипт для миграции на сервере
# Использование: ./migrate_server.sh

set -e  # Остановка при ошибке

echo "=========================================="
echo "МИГРАЦИЯ С POSTGRESQL НА SQLITE"
echo "=========================================="

# Проверка, что мы в правильной директории
if [ ! -f "main.py" ]; then
    echo "❌ Ошибка: файл main.py не найден"
    echo "   Перейдите в директорию проекта"
    exit 1
fi

# Проверка виртуального окружения
if [ ! -d "venv" ]; then
    echo "❌ Ошибка: виртуальное окружение не найдено"
    exit 1
fi

# Активация виртуального окружения
echo "📦 Активация виртуального окружения..."
source venv/bin/activate

# Проверка зависимостей
echo "📦 Проверка зависимостей..."
if ! python -c "import aiosqlite" 2>/dev/null; then
    echo "⚠️  aiosqlite не установлен, устанавливаю..."
    pip install aiosqlite>=0.19.0
fi

if ! python -c "import asyncpg" 2>/dev/null; then
    echo "⚠️  asyncpg не установлен, устанавливаю..."
    pip install asyncpg>=0.29.0
fi

# Остановка бота
echo ""
echo "🛑 Остановка бота..."
if systemctl is-active --quiet parsertaxi-bot 2>/dev/null; then
    echo "   Останавливаю systemd сервис..."
    sudo systemctl stop parsertaxi-bot
    BOT_STOPPED=true
elif pgrep -f "python.*main.py" > /dev/null; then
    echo "   Найден запущенный процесс, останавливаю..."
    pkill -f "python.*main.py"
    sleep 2
    BOT_STOPPED=true
else
    echo "   Бот не запущен"
    BOT_STOPPED=false
fi

# Резервное копирование
echo ""
echo "💾 Создание резервной копии..."
BACKUP_DIR="$HOME/backups/parsertaxi"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/pg_backup_$(date +%Y%m%d_%H%M%S).sql"

# Попытка создать дамп PostgreSQL (если доступен)
if command -v pg_dump &> /dev/null && [ -f ".env" ]; then
    source .env
    if [[ "$DATABASE_URL" == *"postgresql"* ]]; then
        echo "   Создаю дамп PostgreSQL..."
        # Парсим DATABASE_URL (упрощенная версия)
        # В реальности может потребоваться более сложный парсинг
        echo "   ⚠️  Для создания дампа выполните вручную:"
        echo "   pg_dump -h host -U user -d database > $BACKUP_FILE"
    fi
else
    echo "   ⚠️  pg_dump не найден, пропускаю создание дампа"
fi

# Запуск миграции
echo ""
echo "🔄 Запуск миграции..."
if [ ! -f "migrate_to_sqlite.py" ]; then
    echo "❌ Ошибка: файл migrate_to_sqlite.py не найден"
    exit 1
fi

python migrate_to_sqlite.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Миграция завершена успешно!"
    
    # Обновление .env
    echo ""
    echo "📝 Обновление конфигурации..."
    if [ -f ".env" ]; then
        # Создаем резервную копию .env
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        
        # Обновляем DATABASE_URL
        if grep -q "DATABASE_URL" .env; then
            # Определяем абсолютный путь к bot.db
            ABS_DB_PATH=$(readlink -f bot.db 2>/dev/null || echo "$(pwd)/bot.db")
            SQLITE_URL="sqlite+aiosqlite:///$ABS_DB_PATH"
            
            # Заменяем DATABASE_URL
            sed -i.bak "s|DATABASE_URL=.*|DATABASE_URL=$SQLITE_URL|" .env
            echo "   ✅ DATABASE_URL обновлен в .env"
        else
            echo "   ⚠️  DATABASE_URL не найден в .env, добавьте вручную:"
            echo "   DATABASE_URL=sqlite+aiosqlite:///$(pwd)/bot.db"
        fi
    else
        echo "   ⚠️  Файл .env не найден, создайте его вручную"
    fi
    
    # Проверка файла БД
    echo ""
    echo "📊 Проверка результата..."
    if [ -f "bot.db" ]; then
        DB_SIZE=$(du -h bot.db | cut -f1)
        echo "   ✅ Файл bot.db создан (размер: $DB_SIZE)"
        
        # Проверка таблиц
        if command -v sqlite3 &> /dev/null; then
            TABLE_COUNT=$(sqlite3 bot.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "0")
            echo "   ✅ Таблиц в БД: $TABLE_COUNT"
        fi
    else
        echo "   ⚠️  Файл bot.db не найден"
    fi
    
    echo ""
    echo "🎉 Миграция завершена!"
    echo ""
    echo "Следующие шаги:"
    echo "1. Проверьте работу бота: python main.py"
    echo "2. Если все работает, запустите: sudo systemctl start parsertaxi-bot"
    echo "3. Проверьте логи: sudo journalctl -u parsertaxi-bot -f"
    
    # Предложение перезапустить бота
    if [ "$BOT_STOPPED" = true ]; then
        read -p "Запустить бота сейчас? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if systemctl list-unit-files | grep -q parsertaxi-bot; then
                sudo systemctl start parsertaxi-bot
                echo "✅ Бот запущен через systemd"
            else
                echo "⚠️  systemd сервис не настроен, запустите вручную: python main.py"
            fi
        fi
    fi
else
    echo ""
    echo "❌ Миграция завершилась с ошибками"
    echo "   Проверьте логи выше"
    exit 1
fi

