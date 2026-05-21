"""Authentication & user management for TradingAgents Web UI.

Stores users in SQLite (~/.tradingagents/auth.db) with PBKDF2 password hashes.
Also maintains a task_index table for fast owner-based task lookups.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_LOCK = threading.Lock()

_DEFAULT_ADMIN = "admin"
_DEFAULT_USER = "xuliang"
_INITIAL_PASSWORD = "Admin@123!"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _auth_db_path() -> Path:
    return Path.home() / ".tradingagents" / "auth.db"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return pwd_hash, salt


def _verify_password(password: str, pwd_hash: bytes, salt: bytes) -> bool:
    computed, _ = _hash_password(password, salt)
    return computed == pwd_hash


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash BLOB NOT NULL,
    salt BLOB NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
    enabled INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_index (
    task_key TEXT PRIMARY KEY,
    owner_user_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    task_path TEXT,
    status TEXT,
    created_at TEXT,
    FOREIGN KEY (owner_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _get_connection() -> sqlite3.Connection:
    path = _auth_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Auto-create schema on first connection
    conn.executescript(_INIT_SQL)
    conn.commit()
    return conn


def init_auth_db() -> None:
    """Create tables if they do not exist."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.executescript(_INIT_SQL)
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Default users
# ---------------------------------------------------------------------------

def ensure_default_users() -> None:
    """Ensure admin and xuliang exist with initial password."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            for username, role in ((_DEFAULT_ADMIN, "admin"), (_DEFAULT_USER, "user")):
                row = conn.execute(
                    "SELECT id FROM users WHERE username = ?", (username,)
                ).fetchone()
                if row is None:
                    pwd_hash, salt = _hash_password(_INITIAL_PASSWORD)
                    conn.execute(
                        """
                        INSERT INTO users
                        (username, password_hash, salt, role, enabled, must_change_password, created_at)
                        VALUES (?, ?, ?, ?, 1, 1, ?)
                        """,
                        (username, pwd_hash, salt, role, _now_iso()),
                    )
                    logger.info("Created default %s user: %s", role, username)
            conn.commit()
        finally:
            conn.close()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def verify_password(username: str, password: str) -> dict[str, Any] | None:
    """Return user dict if credentials are valid, else None."""
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            if row is None:
                return None
            user = dict(row)
            if not _verify_password(password, user["password_hash"], user["salt"]):
                return None
            if not user["enabled"]:
                return None
            # Do not return sensitive fields
            return _sanitize_user(user)
        finally:
            conn.close()


def _sanitize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in user.items() if k not in ("password_hash", "salt")}


def create_user(
    username: str, password: str, role: str, created_by_admin_id: int
) -> dict[str, Any]:
    """Create a new user. Raises ValueError on invalid input or duplicate name."""
    if not username or not username.strip():
        raise ValueError("用户名不能为空")
    username = username.strip()
    if role not in ("admin", "user"):
        raise ValueError("角色必须是 admin 或 user")
    if len(password) < 6:
        raise ValueError("密码长度不能少于 6 位")

    pwd_hash, salt = _hash_password(password)
    with _DB_LOCK:
        conn = _get_connection()
        try:
            try:
                conn.execute(
                    """
                    INSERT INTO users
                    (username, password_hash, salt, role, enabled, must_change_password, created_at)
                    VALUES (?, ?, ?, ?, 1, 1, ?)
                    """,
                    (username, pwd_hash, salt, role, _now_iso()),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"用户名 '{username}' 已存在") from exc
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            return _sanitize_user(dict(row))
        finally:
            conn.close()


def update_user(user_id: int, **fields: Any) -> dict[str, Any]:
    """Update user fields. Allowed: role, enabled."""
    allowed = {"role", "enabled"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        raise ValueError("无可更新的字段")

    with _DB_LOCK:
        conn = _get_connection()
        try:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [user_id]
            conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise ValueError(f"用户 ID {user_id} 不存在")
            return _sanitize_user(dict(row))
        finally:
            conn.close()


def delete_user(user_id: int, current_admin_id: int) -> None:
    """Delete a user. Protects against deleting self and deleting last admin."""
    if user_id == current_admin_id:
        raise ValueError("不能删除当前登录的管理员自身")

    with _DB_LOCK:
        conn = _get_connection()
        try:
            # Check at least one other enabled admin remains
            admin_count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND enabled = 1"
            ).fetchone()[0]
            target = conn.execute(
                "SELECT role FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if target is None:
                raise ValueError("用户不存在")
            if target["role"] == "admin" and admin_count <= 1:
                raise ValueError("至少保留 1 个启用的管理员")

            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()


def list_users() -> list[dict[str, Any]]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
            return [_sanitize_user(dict(r)) for r in rows]
        finally:
            conn.close()


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return _sanitize_user(dict(row)) if row else None
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Password management
# ---------------------------------------------------------------------------

def change_password(user_id: int, old_password: str, new_password: str) -> None:
    if len(new_password) < 6:
        raise ValueError("新密码长度不能少于 6 位")

    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT password_hash, salt FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                raise ValueError("用户不存在")
            if not _verify_password(old_password, row["password_hash"], row["salt"]):
                raise ValueError("旧密码不正确")

            pwd_hash, salt = _hash_password(new_password)
            conn.execute(
                "UPDATE users SET password_hash = ?, salt = ?, must_change_password = 0 WHERE id = ?",
                (pwd_hash, salt, user_id),
            )
            conn.commit()
        finally:
            conn.close()


def admin_reset_password(user_id: int, new_password: str) -> None:
    if len(new_password) < 6:
        raise ValueError("新密码长度不能少于 6 位")

    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise ValueError("用户不存在")
            pwd_hash, salt = _hash_password(new_password)
            conn.execute(
                "UPDATE users SET password_hash = ?, salt = ?, must_change_password = 1 WHERE id = ?",
                (pwd_hash, salt, user_id),
            )
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Session helper (Streamlit-oriented)
# ---------------------------------------------------------------------------

def require_auth(session_state: dict) -> dict[str, Any]:
    """Return current user from session_state, or raise RuntimeError if not logged in."""
    user = session_state.get("auth_user")
    if not user:
        raise RuntimeError("未登录")
    return user


# ---------------------------------------------------------------------------
# Task index (owner-based lookup)
# ---------------------------------------------------------------------------

def upsert_task_index(
    task_key: str, owner_user_id: int, ticker: str, trade_date: str, task_path: str = "", status: str = ""
) -> None:
    if owner_user_id <= 0:
        return  # Skip for test defaults or unassigned records
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT INTO task_index (task_key, owner_user_id, ticker, trade_date, task_path, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_key) DO UPDATE SET
                    owner_user_id=excluded.owner_user_id,
                    ticker=excluded.ticker,
                    trade_date=excluded.trade_date,
                    task_path=excluded.task_path,
                    status=excluded.status
                """,
                (task_key, owner_user_id, ticker, trade_date, task_path, status, _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()


def delete_task_index(task_key: str) -> None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute("DELETE FROM task_index WHERE task_key = ?", (task_key,))
            conn.commit()
        finally:
            conn.close()


def get_task_keys_for_user(user_id: int) -> set[str]:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT task_key FROM task_index WHERE owner_user_id = ?", (user_id,)
            ).fetchall()
            return {r["task_key"] for r in rows}
        finally:
            conn.close()


def get_task_owner(task_key: str) -> int | None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT owner_user_id FROM task_index WHERE task_key = ?", (task_key,)
            ).fetchone()
            return row["owner_user_id"] if row else None
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------

def _get_migration_version() -> int:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'migration_version'"
            ).fetchone()
            return int(row["value"]) if row else 0
        finally:
            conn.close()


def _set_migration_version(version: int) -> None:
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('migration_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(version),),
            )
            conn.commit()
        finally:
            conn.close()


def run_legacy_migration() -> dict[str, Any]:
    """One-time migration: assign all existing tasks to user 'xuliang'.

    Returns {"migrated": int, "skipped": int}
    """
    init_auth_db()
    ensure_default_users()

    current_version = _get_migration_version()
    if current_version >= 1:
        return {"migrated": 0, "skipped": 0, "reason": "already_migrated"}

    # Resolve xuliang user id
    with _DB_LOCK:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (_DEFAULT_USER,)
            ).fetchone()
            owner_id = row["id"] if row else None
        finally:
            conn.close()

    if owner_id is None:
        return {"migrated": 0, "skipped": 0, "reason": "xuliang_not_found"}

    migrated = 0
    skipped = 0
    seen_keys: set[str] = set()

    # 1. Scan web_tasks
    web_tasks_root = Path.home() / ".tradingagents" / "web_tasks"
    if web_tasks_root.exists():
        for path in web_tasks_root.rglob("*.json"):
            try:
                import json
                data = json.loads(path.read_text(encoding="utf-8"))
                ticker = data.get("ticker", path.parent.name)
                trade_date = data.get("trade_date", path.stem)
                key = f"{ticker}__{trade_date}"
                if key in seen_keys:
                    skipped += 1
                    continue
                seen_keys.add(key)
                upsert_task_index(key, owner_id, ticker, trade_date, str(path), data.get("status", ""))
                migrated += 1
            except Exception as exc:
                logger.warning("Migration skip web_task %s: %s", path, exc)
                skipped += 1

    # 2. Scan full-state logs
    logs_root = Path.home() / ".tradingagents" / "logs"
    if logs_root.exists():
        for log_file in logs_root.rglob("full_states_log_*.json"):
            try:
                m = re.search(r"full_states_log_(\d{4}-\d{2}-\d{2})\.json$", log_file.name)
                if not m:
                    continue
                trade_date = m.group(1)
                ticker = log_file.parent.parent.name
                key = f"{ticker}__{trade_date}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                upsert_task_index(key, owner_id, ticker, trade_date, str(log_file), "")
                migrated += 1
            except Exception as exc:
                logger.warning("Migration skip log %s: %s", log_file, exc)
                skipped += 1

    # 3. Scan legacy CLI dirs
    if logs_root.exists():
        for ticker_dir in logs_root.iterdir():
            if not ticker_dir.is_dir():
                continue
            for date_dir in ticker_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_dir.name):
                    continue
                ticker = ticker_dir.name
                trade_date = date_dir.name
                key = f"{ticker}__{trade_date}"
                if key in seen_keys:
                    continue
                # Only migrate if there are legacy artifacts inside
                report_dir = date_dir / "reports"
                msg_log = date_dir / "message_tool.log"
                if report_dir.exists() or msg_log.exists():
                    seen_keys.add(key)
                    upsert_task_index(key, owner_id, ticker, trade_date, "", "")
                    migrated += 1

    _set_migration_version(1)
    logger.info("Legacy migration done: migrated=%d, skipped=%d", migrated, skipped)
    return {"migrated": migrated, "skipped": skipped, "reason": "ok"}
