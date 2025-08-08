# chat_repo.py
from typing import Optional, List, Dict, Any
from sqlalchemy import text
from db.db import get_session
import json

# --- Chats
async def ensure_chat(chat_id: int, chat_type: str, title: Optional[str]):
    async with get_session() as s:
        await s.execute(text("""
            INSERT INTO chats (chat_id, chat_type, title)
            VALUES (:cid, :ctype, :title)
            ON CONFLICT (chat_id) DO NOTHING
        """), {"cid": chat_id, "ctype": chat_type, "title": title})
        await s.commit()

async def load_chat_config(chat_id: int) -> Dict[str, Any]:
    async with get_session() as s:
        row = (await s.execute(text("""
          SELECT system_prompt, history_limit, autopost_enabled, autopost_interval,
                 reactions_enabled, muted_until, settings
          FROM chats WHERE chat_id=:cid
        """), {"cid": chat_id})).mappings().first()
        return dict(row) if row else {}

async def save_chat_config(chat_id: int, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k}=:{k}" for k in fields.keys())
    async with get_session() as s:
        await s.execute(text(f"""
          UPDATE chats SET {sets}, updated_at=now() WHERE chat_id=:cid
        """), {"cid": chat_id, **fields})
        await s.commit()

# --- History
async def append_message(chat_id: int, role: str, content: str, history_limit: int):
    async with get_session() as s:
        await s.execute(text("""
          INSERT INTO chat_messages (chat_id, role, content)
          VALUES (:cid, :role, :content)
        """), {"cid": chat_id, "role": role, "content": content})
        # Trim tail
        await s.execute(text("""
          DELETE FROM chat_messages
          WHERE chat_id=:cid AND id NOT IN (
            SELECT id FROM chat_messages
            WHERE chat_id=:cid ORDER BY id DESC LIMIT :lim
          )
        """), {"cid": chat_id, "lim": history_limit})
        await s.commit()

async def load_history(chat_id: int, limit: int) -> List[Dict[str, str]]:
    async with get_session() as s:
        rows = (await s.execute(text("""
          SELECT role, content FROM chat_messages
          WHERE chat_id=:cid ORDER BY id DESC LIMIT :lim
        """), {"cid": chat_id, "lim": limit})).mappings().all()
        return list(reversed([{"role": r["role"], "content": r["content"]} for r in rows]))

async def clear_history(chat_id: int):
    async with get_session() as s:
        await s.execute(text("DELETE FROM chat_messages WHERE chat_id=:cid"), {"cid": chat_id})
        await s.commit()

# --- Holidays
async def was_holiday_sent_today(chat_id: int, date_str):
    async with get_session() as s:
        row = (await s.execute(text("""
            SELECT 1 FROM holiday_log WHERE chat_id=:cid AND sent_date=:d
        """), {"cid": chat_id, "d": date_str})).first()
        return row is not None

async def mark_holiday_sent(chat_id: int, date_str):
    async with get_session() as s:
        await s.execute(text("""
            INSERT INTO holiday_log (chat_id, sent_date)
            VALUES (:cid, :d) ON CONFLICT DO NOTHING
        """), {"cid": chat_id, "d": date_str})
        await s.commit()

# --- Metrics (минимум)
async def load_metrics(chat_id: int) -> dict:
    async with get_session() as s:
        row = (await s.execute(text("""
            SELECT message_counter, user_streaks, responded_message_ids, reply_counts,
                   reaction_counts, last_streak_response_time
            FROM chat_metrics WHERE chat_id=:cid
        """), {"cid": chat_id})).mappings().first()
        return dict(row) if row else {}

def prepare_json_data(data):
    if isinstance(data, dict):
        return {k: list(v) if isinstance(v, tuple) else v for k, v in data.items()}
    elif isinstance(data, list):
        return [list(i) if isinstance(i, tuple) else i for i in data]
    return data

async def save_metrics(chat_id, metrics):
    # Подготовка данных
    metrics_prepared = {
        "chat_id": chat_id,
        "message_counter": metrics.get("message_counter", 0),
        "user_streaks": json.dumps(prepare_json_data(metrics.get("user_streaks", {}))),
        "responded_message_ids": json.dumps(prepare_json_data(metrics.get("responded_message_ids", []))),
        "reply_counts": json.dumps(prepare_json_data(metrics.get("reply_counts", {}))),
        "reaction_counts": json.dumps(prepare_json_data(metrics.get("reaction_counts", {}))),
        "last_streak_response_time": metrics.get("last_streak_response_time", 0)
    }

    async with get_session() as s:
        await s.execute(text("""
            INSERT INTO chat_metrics (chat_id, message_counter, user_streaks, responded_message_ids,
                                    reply_counts, reaction_counts, last_streak_response_time)
            VALUES (:chat_id, :message_counter, :user_streaks, :responded_message_ids,
                    :reply_counts, :reaction_counts, :last_streak_response_time)
            ON CONFLICT (chat_id) DO UPDATE SET
                message_counter=:message_counter,
                user_streaks=:user_streaks,
                responded_message_ids=:responded_message_ids,
                reply_counts=:reply_counts,
                reaction_counts=:reaction_counts,
                last_streak_response_time=:last_streak_response_time
        """), metrics_prepared)
        await s.commit()
