# Руководство по миграции с PostgreSQL на SQLite

Это руководство поможет вам перенести данные бота с PostgreSQL на SQLite.

## Подготовка к миграции

### 1. Подключитесь к серверу по SSH

```bash
ssh user@your-server-ip
```

### 2. Перейдите в директорию проекта

```bash
cd /path/to/parsertaxi
# или
cd ~/parsertaxi
```

### 3. Активируйте виртуальное окружение

```bash
source venv/bin/activate
```

### 4. Убедитесь, что установлены все зависимости

```bash
pip install -r requirements.txt
```

Убедитесь, что в `requirements.txt` есть:
- `aiosqlite>=0.19.0`
- `sqlalchemy>=2.0.0`

## Резервное копирование данных

**ВАЖНО:** Перед миграцией обязательно создайте резервную копию!

### Резервная копия PostgreSQL

```bash
# Создайте директорию для бэкапов
mkdir -p ~/backups/parsertaxi

# Создайте дамп базы данных
# Извлеките данные из DATABASE_URL в .env
# Формат: postgresql+asyncpg://user:password@host:port/database
pg_dump -h localhost -U postgres_user -d database_name > ~/backups/parsertaxi/pg_backup_$(date +%Y%m%d_%H%M%S).sql

# Или если используете переменную окружения:
source .env
# Парсим DATABASE_URL и создаем дамп
pg_dump -h host -U user -d database > ~/backups/parsertaxi/pg_backup_$(date +%Y%m%d_%H%M%S).sql
```

## Выполнение миграции

### Вариант 1: Автоматическая миграция (рекомендуется)

1. **Остановите бота** (если он запущен):

```bash
# Если используете systemd
sudo systemctl stop parsertaxi-bot

# Или найдите процесс и остановите его
ps aux | grep "python.*main.py"
kill <PID>
```

2. **Запустите скрипт миграции**:

```bash
python migrate_to_sqlite.py
```

Скрипт автоматически:
- Подключится к PostgreSQL
- Создаст файл SQLite (`bot.db`)
- Создаст все необходимые таблицы
- Перенесет все данные

3. **Проверьте результат**:

```bash
# Проверьте размер файла БД
ls -lh bot.db

# Проверьте содержимое (опционально)
sqlite3 bot.db "SELECT COUNT(*) FROM chats;"
sqlite3 bot.db "SELECT COUNT(*) FROM chat_messages;"
```

### Вариант 2: Ручная миграция

Если автоматический скрипт не работает, выполните вручную:

1. **Экспорт данных из PostgreSQL**:

```bash
# Экспорт таблицы chats
psql -h localhost -U user -d database -c "COPY chats TO STDOUT WITH CSV HEADER" > chats.csv

# Экспорт таблицы chat_messages
psql -h localhost -U user -d database -c "COPY chat_messages TO STDOUT WITH CSV HEADER" > chat_messages.csv

# И так далее для всех таблиц
```

2. **Создание SQLite базы**:

```bash
# Создайте таблицы
sqlite3 bot.db < schema.sql
```

3. **Импорт данных** (требует дополнительной обработки из-за различий в типах данных)

## Обновление конфигурации

### 1. Обновите .env файл

```bash
nano .env
```

Измените `DATABASE_URL`:

```env
# Старое значение (PostgreSQL)
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/database

# Новое значение (SQLite)
DATABASE_URL=sqlite+aiosqlite:///./bot.db

# Или с абсолютным путем
DATABASE_URL=sqlite+aiosqlite:////opt/parsertaxi/bot.db
```

### 2. Проверьте права доступа к файлу БД

```bash
# Убедитесь, что файл доступен для записи
chmod 644 bot.db

# Если бот запускается от другого пользователя, установите правильного владельца
sudo chown bot_user:bot_user bot.db
```

## Тестирование

### 1. Запустите бота в тестовом режиме

```bash
# Активируйте виртуальное окружение
source venv/bin/activate

# Запустите бота
python main.py
```

Проверьте логи на наличие ошибок.

### 2. Проверьте работу команд

Отправьте боту команду `/help` и проверьте, что все работает.

### 3. Проверьте данные

```bash
# Проверьте количество чатов
sqlite3 bot.db "SELECT COUNT(*) FROM chats;"

# Проверьте количество сообщений
sqlite3 bot.db "SELECT COUNT(*) FROM chat_messages;"

# Проверьте пользователей
sqlite3 bot.db "SELECT * FROM users;"
```

## Запуск в продакшене

Если все работает корректно:

```bash
# Запустите бота через systemd
sudo systemctl start parsertaxi-bot

# Проверьте статус
sudo systemctl status parsertaxi-bot

# Просмотрите логи
sudo journalctl -u parsertaxi-bot -f
```

## Откат (если что-то пошло не так)

Если миграция не удалась, вы можете вернуться к PostgreSQL:

1. **Восстановите .env файл**:

```bash
# Верните старый DATABASE_URL
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/database
```

2. **Восстановите данные из резервной копии** (если нужно):

```bash
psql -h localhost -U user -d database < ~/backups/parsertaxi/pg_backup_YYYYMMDD_HHMMSS.sql
```

3. **Перезапустите бота**

## Преимущества SQLite

После миграции вы получите:

- ✅ **Простота развертывания** - не нужен отдельный сервер БД
- ✅ **Меньше ресурсов** - SQLite легковесный
- ✅ **Простое резервное копирование** - просто скопируйте файл `bot.db`
- ✅ **Автоматическое создание** - файл БД создается автоматически

## Резервное копирование SQLite

После миграции настройте регулярное резервное копирование:

```bash
# Создайте скрипт backup.sh
cat > ~/backup_bot.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backup/parsertaxi"
DATE=$(date +%Y%m%d_%H%M%S)
cp /path/to/parsertaxi/bot.db "$BACKUP_DIR/backup_$DATE.db"
# Храним последние 7 дней
find "$BACKUP_DIR" -name "backup_*.db" -mtime +7 -delete
EOF

chmod +x ~/backup_bot.sh

# Добавьте в crontab (ежедневно в 2:00)
crontab -e
# Добавьте строку:
# 0 2 * * * /path/to/backup_bot.sh
```

## Устранение проблем

### Ошибка "database is locked"

SQLite блокирует БД при записи. Убедитесь, что:
- Только один процесс бота запущен
- Нет других процессов, использующих БД

### Ошибка "no such table"

Убедитесь, что таблицы созданы:
```bash
sqlite3 bot.db ".tables"
```

Если таблиц нет, выполните:
```bash
sqlite3 bot.db < schema.sql
```

### Проблемы с правами доступа

```bash
# Проверьте права
ls -la bot.db

# Установите правильные права
chmod 644 bot.db
chown bot_user:bot_user bot.db
```

## Дополнительная информация

- Документация SQLite: https://www.sqlite.org/docs.html
- Документация aiosqlite: https://aiosqlite.omnilib.dev/

