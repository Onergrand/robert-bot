-- Миграция: добавление таблицы users для системы ролей
-- Выполните этот скрипт если таблица users не существует

-- Для PostgreSQL
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user' CHECK(role IN ('owner', 'admin', 'user')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- Для SQLite (если используете SQLite, используйте schema.sql)
-- CREATE TABLE IF NOT EXISTS users (
--     user_id INTEGER PRIMARY KEY,
--     username TEXT,
--     role TEXT DEFAULT 'user' CHECK(role IN ('owner', 'admin', 'user')),
--     created_at TEXT DEFAULT CURRENT_TIMESTAMP,
--     updated_at TEXT DEFAULT CURRENT_TIMESTAMP
-- );
-- 
-- CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

