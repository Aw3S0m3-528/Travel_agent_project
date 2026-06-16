import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.state import TravelState


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "travel_agent.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """
    初始化本地 SQLite 数据库。
    """

    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS itinerary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_input TEXT NOT NULL,
                destination TEXT,
                travel_days INTEGER,
                budget TEXT,
                preferences TEXT,
                route_plan TEXT,
                time_plan TEXT,
                final_guide TEXT,
                validation_result TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                namespace TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (namespace, cache_key)
            )
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(itinerary)").fetchall()
        }
        if "state_json" not in columns:
            conn.execute("ALTER TABLE itinerary ADD COLUMN state_json TEXT")
        conn.commit()
    finally:
        conn.close()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except json.JSONDecodeError:
        return default


def _parse_itinerary_row(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    item["preferences"] = _json_loads(item.get("preferences"), [])
    item["route_plan"] = _json_loads(item.get("route_plan"), {})
    item["time_plan"] = _json_loads(item.get("time_plan"), {})
    item["state_json"] = _json_loads(item.get("state_json"), {})
    return item


def save_itinerary(state: TravelState) -> int:
    """
    保存一次生成结果，返回 itinerary_id。
    """

    init_db()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO itinerary (
                user_input,
                destination,
                travel_days,
                budget,
                preferences,
                route_plan,
                time_plan,
                final_guide,
                validation_result,
                state_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.get("user_input", ""),
                state.get("destination", ""),
                state.get("travel_days", 0),
                state.get("budget", ""),
                _json_dumps(state.get("preferences", [])),
                _json_dumps(state.get("route_plan", {})),
                _json_dumps(state.get("time_plan", {})),
                state.get("final_guide", ""),
                state.get("validation_result", ""),
                _json_dumps(state),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_recent_itineraries(limit: int = 5) -> List[Dict[str, Any]]:
    """
    获取最近生成的行程摘要。
    """

    init_db()

    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                id,
                destination,
                travel_days,
                budget,
                preferences,
                created_at
            FROM itinerary
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        results.append(_parse_itinerary_row(row))

    return results


def get_itinerary(itinerary_id: int) -> Optional[Dict[str, Any]]:
    """
    获取单条完整行程详情。
    """

    init_db()

    conn = get_connection()
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                id,
                user_input,
                destination,
                travel_days,
                budget,
                preferences,
                route_plan,
                time_plan,
                final_guide,
                validation_result,
                state_json,
                created_at
            FROM itinerary
            WHERE id = ?
            """,
            (itinerary_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return _parse_itinerary_row(row)


def get_cache(namespace: str, cache_key: str) -> Optional[Any]:
    init_db()

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM cache WHERE namespace = ? AND cache_key = ?",
            (namespace, cache_key),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return _json_loads(row[0], None)


def set_cache(namespace: str, cache_key: str, value: Any) -> None:
    init_db()

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO cache (namespace, cache_key, value, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (namespace, cache_key, _json_dumps(value)),
        )
        conn.commit()
    finally:
        conn.close()
