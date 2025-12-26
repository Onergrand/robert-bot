# Быстрая миграция на SQLite (для сервера)

## Быстрый старт (3 команды)

```bash
# 1. Подключитесь к серверу
ssh user@your-server-ip

# 2. Перейдите в директорию проекта
cd /path/to/parsertaxi

# 3. Запустите автоматический скрипт миграции
./migrate_server.sh
```

Скрипт автоматически:
- ✅ Остановит бота
- ✅ Создаст резервную копию
- ✅ Перенесет данные из PostgreSQL в SQLite
- ✅ Обновит конфигурацию
- ✅ Проверит результат

## Ручная миграция (если скрипт не работает)

### Шаг 1: Подготовка

```bash
# Подключитесь к серверу
ssh user@your-server-ip

# Перейдите в директорию проекта
cd /path/to/parsertaxi

# Активируйте виртуальное окружение
source venv/bin/activate

# Установите зависимости (если нужно)
pip install aiosqlite asyncpg
```

### Шаг 2: Остановка бота

```bash
# Если используете systemd
sudo systemctl stop parsertaxi-bot

# Или найдите и остановите процесс
ps aux | grep "python.*main.py"
kill <PID>
```

### Шаг 3: Резервное копирование

```bash
# Создайте директорию для бэкапов
mkdir -p ~/backups/parsertaxi

# Создайте дамп PostgreSQL (замените параметры на свои)
pg_dump -h localhost -U postgres_user -d database_name > ~/backups/parsertaxi/pg_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Шаг 4: Запуск миграции

```bash
# Запустите скрипт миграции
python migrate_to_sqlite.py
```

### Шаг 5: Обновление конфигурации

```bash
# Отредактируйте .env файл
nano .env

# Измените DATABASE_URL на:
DATABASE_URL=sqlite+aiosqlite:///./bot.db

# Или с абсолютным путем:
DATABASE_URL=sqlite+aiosqlite:////opt/parsertaxi/bot.db
```

### Шаг 6: Проверка

```bash
# Проверьте размер файла БД
ls -lh bot.db

# Проверьте количество записей
sqlite3 bot.db "SELECT COUNT(*) FROM chats;"
sqlite3 bot.db "SELECT COUNT(*) FROM chat_messages;"
```

### Шаг 7: Запуск бота

```bash
# Тестовый запуск
python main.py

# Если все работает, запустите через systemd
sudo systemctl start parsertaxi-bot
sudo systemctl status parsertaxi-bot
```

## Проверка после миграции

```bash
# Проверьте логи
sudo journalctl -u parsertaxi-bot -f

# Проверьте работу команд бота
# Отправьте /help в Telegram
```

## Откат (если что-то пошло не так)

```bash
# Восстановите .env
nano .env
# Верните старый DATABASE_URL: postgresql+asyncpg://...

# Восстановите данные (если нужно)
psql -h localhost -U user -d database < ~/backups/parsertaxi/pg_backup_*.sql

# Перезапустите бота
sudo systemctl restart parsertaxi-bot
```

## Важные замечания

1. **Резервное копирование обязательно** - создайте дамп перед миграцией
2. **Остановите бота** - не мигрируйте при работающем боте
3. **Проверьте результат** - убедитесь, что данные перенесены
4. **Тестируйте** - запустите бота в тестовом режиме перед продакшеном

## Проблемы?

Смотрите подробное руководство: `MIGRATION_GUIDE.md`

