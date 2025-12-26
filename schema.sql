-- SQL схема для Telegram бота ParserTaxi (SQLite)
-- Выполните этот скрипт для создания всех необходимых таблиц в SQLite
-- SQLite автоматически создает файл БД при первом подключении

-- Включение внешних ключей (важно для SQLite)
PRAGMA foreign_keys = ON;

-- Таблица чатов
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    chat_type TEXT,
    title TEXT,
    system_prompt TEXT,
    history_limit INTEGER DEFAULT 10,
    autopost_enabled INTEGER DEFAULT 0,  -- BOOLEAN как INTEGER в SQLite (0/1)
    autopost_interval INTEGER,
    reactions_enabled INTEGER DEFAULT 1,
    muted_until TEXT,  -- TIMESTAMP как TEXT в SQLite
    settings TEXT,  -- JSON как TEXT в SQLite
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Таблица сообщений чата
-- ВАЖНО: Все сообщения сохраняются без ограничений
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_id ON chat_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at DESC);

-- Таблица лога отправленных праздничных сообщений
CREATE TABLE IF NOT EXISTS holiday_log (
    chat_id INTEGER NOT NULL,
    sent_date TEXT NOT NULL,  -- DATE как TEXT в SQLite
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chat_id, sent_date),
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_holiday_log_sent_date ON holiday_log(sent_date);

-- Таблица метрик чата
CREATE TABLE IF NOT EXISTS chat_metrics (
    chat_id INTEGER PRIMARY KEY REFERENCES chats(chat_id) ON DELETE CASCADE,
    message_counter INTEGER DEFAULT 0,
    user_streaks TEXT DEFAULT '{}',  -- JSON как TEXT
    responded_message_ids TEXT DEFAULT '[]',
    reply_counts TEXT DEFAULT '{}',
    reaction_counts TEXT DEFAULT '{}',
    last_streak_response_time INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Таблица пользователей с ролями
-- Роли: 'owner', 'admin', 'user' (по умолчанию 'user')
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    role TEXT DEFAULT 'user' CHECK(role IN ('owner', 'admin', 'user')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
