# ParserTaxi Telegram Bot

Telegram бот с поддержкой AI-ответов, праздничных поздравлений и метрик.

## Требования

- Python 3.11 или выше
- pip
- SQLite 3 (обычно встроен в Python)

**Примечание:** Бот использует SQLite для хранения данных. Это упрощает развертывание и экономит ресурсы - не требуется отдельный сервер БД.

## Установка и развертывание на сервере

### 1. Установка зависимостей системы

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# CentOS/RHEL
sudo yum install -y python3.11 python3-pip
```

### 2. Клонирование и настройка проекта

```bash
# Клонируйте репозиторий (или загрузите файлы на сервер)
cd /opt
git clone <your-repo-url> parsertaxi
cd parsertaxi

# Создайте виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Инициализация базы данных

```bash
# SQLite создаст файл БД автоматически при первом запуске
# Но можно создать таблицы заранее:
sqlite3 bot.db < schema.sql

# Или файл создастся автоматически при первом запуске бота
```

### 4. Настройка переменных окружения

```bash
# Скопируйте пример файла
cp env.example.txt .env

# Отредактируйте .env файл
nano .env
```

Заполните следующие переменные:
- `TELEGRAM_TOKEN` - токен бота от @BotFather
- `DATABASE_URL` - строка подключения к SQLite (по умолчанию: `sqlite+aiosqlite:///./bot.db`)

### 5. Запуск бота

#### Ручной запуск (для тестирования)

```bash
source venv/bin/activate
python main.py
```

#### Автозапуск через systemd (рекомендуется)

Создайте файл `/etc/systemd/system/parsertaxi-bot.service`:

```ini
[Unit]
Description=ParserTaxi Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/opt/parsertaxi
Environment="PATH=/opt/parsertaxi/venv/bin"
ExecStart=/opt/parsertaxi/venv/bin/python /opt/parsertaxi/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Активируйте и запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable parsertaxi-bot
sudo systemctl start parsertaxi-bot

# Проверка статуса
sudo systemctl status parsertaxi-bot

# Просмотр логов
sudo journalctl -u parsertaxi-bot -f
```

### 6. Проверка работы

```bash
# Проверьте логи
sudo journalctl -u parsertaxi-bot -n 50

# Проверьте файл БД (если используете SQLite)
sqlite3 bot.db "SELECT COUNT(*) FROM chats;"
```

## Структура проекта

```
ParserTaxi/
├── main.py              # Точка входа, настройка бота
├── bot_commands.py      # Команды бота
├── message.py           # Обработка сообщений
├── scoring.py           # Система оценки
├── holiday_evaluator.py # Оценка праздников
├── db/
│   ├── db.py           # Подключение к БД
│   └── chat_repo.py    # Репозиторий для работы с данными
├── utils/
│   └── constants.py    # Константы (праздники)
├── requirements.txt     # Зависимости Python
├── schema.sql          # SQL схема БД
├── .env.example        # Пример переменных окружения
└── README.md           # Документация
```

## Команды бота

- `/start` - Приветствие
- `/help` - Список команд
- `/set_prompt` - Установить системный промпт
- `/get_prompt` - Получить текущий промпт
- `/reset_prompt` - Сбросить промпт
- `/set_history_limit` - Установить лимит истории
- `/status` - Статус бота в чате
- `/metrics` - Метрики чата
- `/holiday_check` - Проверить праздники
- `/mute` / `/unmute` - Заглушить/включить бота
- И другие...

## Устранение проблем

### Бот не запускается

1. Проверьте токен в `.env`
2. Проверьте подключение к БД: `psql -U user -d database -c "SELECT 1;"`
3. Проверьте логи: `sudo journalctl -u parsertaxi-bot -n 100`

### Ошибки подключения к БД

1. Убедитесь, что файл БД существует и доступен для записи
2. Проверьте `DATABASE_URL` в `.env` (путь к файлу БД)
3. Проверьте права доступа к файлу БД: `ls -la bot.db`
4. Убедитесь, что таблицы созданы: `sqlite3 bot.db ".tables"`
5. Если файл БД поврежден, удалите его и перезапустите бота (таблицы создадутся автоматически)

### Бот не отвечает

1. Проверьте логи на ошибки
2. Убедитесь, что бот добавлен в чат и имеет права на отправку сообщений
3. Проверьте, не заглушен ли бот командой `/mute`

## Резервное копирование

Рекомендуется настроить регулярное резервное копирование БД:

```bash
# Создайте скрипт backup.sh
#!/bin/bash
BACKUP_DIR="/backup/parsertaxi"
DATE=$(date +%Y%m%d_%H%M%S)
cp bot.db "$BACKUP_DIR/backup_$DATE.db"

# Или используйте sqlite3 для создания дампа:
# sqlite3 bot.db ".backup '$BACKUP_DIR/backup_$DATE.db'"

# Добавьте в crontab (ежедневно в 2:00)
# 0 2 * * * /path/to/backup.sh
```

**Важно:** SQLite хранит все данные в одном файле (`bot.db`), что упрощает резервное копирование - просто скопируйте файл.

## Лицензия

[Укажите лицензию, если есть]

