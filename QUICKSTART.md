# Быстрый старт - Развертывание на сервере

## Минимальные шаги для запуска

### 1. Установите зависимости системы
```bash
sudo apt-get install python3.11 python3.11-venv
```

### 2. Настройте проект
```bash
# Клонируйте/загрузите проект
cd /opt/parsertaxi

# Создайте виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt
```

### 3. Создайте таблицы БД (опционально)
```bash
# SQLite создаст файл автоматически, но можно создать таблицы заранее:
sqlite3 bot.db < schema.sql
```

### 4. Настройте переменные окружения
```bash
# Создайте .env файл
cp env.example.txt .env
nano .env  # Заполните TELEGRAM_TOKEN (DATABASE_URL опционален, по умолчанию используется SQLite)
```

### 5. Запустите бота

**Тестовый запуск:**
```bash
source venv/bin/activate
python main.py
```

**Автозапуск через systemd:**
```bash
# Отредактируйте parsertaxi-bot.service (укажите правильного пользователя и путь)
sudo nano parsertaxi-bot.service

# Скопируйте в systemd
sudo cp parsertaxi-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable parsertaxi-bot
sudo systemctl start parsertaxi-bot

# Проверьте статус
sudo systemctl status parsertaxi-bot
```

## Проверка работы

```bash
# Логи
sudo journalctl -u parsertaxi-bot -f

# Проверка БД (SQLite)
sqlite3 bot.db "SELECT COUNT(*) FROM chats;"
```

## Важные моменты

1. **TELEGRAM_TOKEN** - получите у [@BotFather](https://t.me/BotFather) в Telegram
2. **DATABASE_URL** - опционально, по умолчанию: `sqlite+aiosqlite:///./bot.db`
3. Убедитесь, что Python 3.11+ установлен: `python3.11 --version`
4. Проверьте права доступа к файлам проекта и файлу БД (`bot.db`)

## Проблемы?

Смотрите раздел "Устранение проблем" в README.md

