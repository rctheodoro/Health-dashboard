#!/usr/bin/env python3
"""
Garmin integration backed by the local garmin-givemydata SQLite database.

This module intentionally keeps the same public API as the old fetcher:
- fetch_garmin_current()
- fetch_garmin_history(days=30)

Data is read directly from:
    /Users/rtbot/.garmin-givemydata/garmin.db
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
import shutil
from typing import Any

GARMIN_DB_PATH = Path("/Users/rtbot/.garmin-givemydata/garmin.db")


def _connect() -> sqlite3.Connection | None:
    """Open the Garmin SQLite database in read-only mode when possible."""
    if not GARMIN_DB_PATH.exists():
        print(f"  ⚠ Garmin database not found: {GARMIN_DB_PATH}")
        return None

    try:
        # Read-only URI mode avoids creating side files and is sufficient here.
        conn = sqlite3.connect(f"file:{GARMIN_DB_PATH}?mode=ro", uri=True)
        conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        return conn
    except Exception as exc:
        try:
            temp_db_path = Path(tempfile.gettempdir()) / "garmin-fetcher.db"
            shutil.copy2(GARMIN_DB_PATH, temp_db_path)
            conn = sqlite3.connect(temp_db_path)
            conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
            return conn
        except Exception as fallback_exc:
            print(f"  ⚠ Garmin database open error: {exc}")
            print(f"  ⚠ Garmin temp-copy fallback failed: {fallback_exc}")
            return None


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _first_existing_table(conn: sqlite3.Connection, *table_names: str) -> str | None:
    for table_name in table_names:
        if _table_exists(conn, table_name):
            return table_name
    return None


def _fetch_one(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[Any, ...] = (),
) -> sqlite3.Row | None:
    try:
        return conn.execute(query, params).fetchone()
    except Exception as exc:
        print(f"  ⚠ Garmin query error: {exc}")
        return None


def _fetch_all(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[Any, ...] = (),
) -> list[sqlite3.Row]:
    try:
        return conn.execute(query, params).fetchall()
    except Exception as exc:
        print(f"  ⚠ Garmin query error: {exc}")
        return []


def _parse_json(raw_value: Any) -> dict[str, Any]:
    if not raw_value:
        return {}

    if isinstance(raw_value, dict):
        return raw_value

    try:
        parsed = json.loads(raw_value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _safe_get(data: Any, *keys: str, default: Any = None) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _value_from_row(row: sqlite3.Row | None, key: str) -> Any:
    if row is None:
        return None
    try:
        return row[key]
    except Exception:
        return None


def _fetch_stats(conn: sqlite3.Connection, date_str: str) -> dict[str, Any] | None:
    """Fetch daily stats from daily_summary."""
    try:
        row = _fetch_one(
            conn,
            """
            SELECT *
            FROM daily_summary
            WHERE calendar_date = ?
            """,
            (date_str,),
        )
        if row is None:
            return None

        return {
            "totalSteps": _value_from_row(row, "total_steps"),
            "restingHeartRate": _value_from_row(row, "resting_heart_rate"),
            "averageHeartRate": None,
            "maxHeartRate": _value_from_row(row, "max_heart_rate"),
            "minHeartRate": _value_from_row(row, "min_heart_rate"),
            "averageStressLevel": _value_from_row(row, "average_stress_level"),
            "bodyBatteryCharged": _value_from_row(row, "body_battery_charged"),
            "bodyBatteryDrained": _value_from_row(row, "body_battery_drained"),
            "totalKilocalories": _value_from_row(row, "total_kilocalories"),
            "activeKilocalories": _value_from_row(row, "active_kilocalories"),
            "bmrKilocalories": _value_from_row(row, "bmr_kilocalories"),
        }
    except Exception as exc:
        print(f"  ⚠ Garmin stats error: {exc}")
        return None


def _fetch_hrv(conn: sqlite3.Connection, date_str: str) -> dict[str, Any] | None:
    """Fetch HRV data from hrv/hrv_status, falling back to sleep raw_json."""
    table_name = _first_existing_table(conn, "hrv_status", "hrv")
    if table_name:
        try:
            row = _fetch_one(
                conn,
                f"SELECT * FROM {table_name} WHERE calendar_date = ?",
                (date_str,),
            )
            if row is not None:
                overnight = (
                    _value_from_row(row, "avgOvernightHrv")
                    or _value_from_row(row, "last_night_avg")
                    or _value_from_row(row, "last_night")
                )
                weekly = (
                    _value_from_row(row, "weeklyAvg")
                    or _value_from_row(row, "weekly_avg")
                    or _value_from_row(row, "hrv_weekly_average")
                )
                status = _value_from_row(row, "status") or _value_from_row(row, "hrvStatus")
                return {
                    "avgOvernightHrv": overnight,
                    "weeklyAvg": weekly,
                    "hrvStatus": status,
                }
        except Exception as exc:
            print(f"  ⚠ Garmin HRV error: {exc}")

    try:
        sleep_row = _fetch_one(
            conn,
            "SELECT raw_json FROM sleep WHERE calendar_date = ?",
            (date_str,),
        )
        sleep_data = _parse_json(_value_from_row(sleep_row, "raw_json"))
        if sleep_data:
            return {
                "avgOvernightHrv": sleep_data.get("avgOvernightHrv"),
                "weeklyAvg": None,
                "hrvStatus": sleep_data.get("hrvStatus"),
            }
    except Exception as exc:
        print(f"  ⚠ Garmin HRV fallback error: {exc}")

    return None


def _fetch_sleep(conn: sqlite3.Connection, date_str: str) -> dict[str, Any] | None:
    """Fetch sleep data from sleep, using raw_json to recover the score."""
    try:
        row = _fetch_one(
            conn,
            """
            SELECT *
            FROM sleep
            WHERE calendar_date = ?
            """,
            (date_str,),
        )
        if row is None:
            return None

        raw_data = _parse_json(_value_from_row(row, "raw_json"))
        score = (
            _safe_get(raw_data, "dailySleepDTO", "sleepScores", "overall", "value")
            or _safe_get(raw_data, "dailySleepDTO", "sleepScores", "totalSleep", "value")
        )

        return {
            "score": score,
            "total_sleep_s": _value_from_row(row, "sleep_time_seconds"),
            "deep_sleep_s": _value_from_row(row, "deep_sleep_seconds"),
            "rem_sleep_s": _value_from_row(row, "rem_sleep_seconds"),
            "light_sleep_s": _value_from_row(row, "light_sleep_seconds"),
        }
    except Exception as exc:
        print(f"  ⚠ Garmin sleep error: {exc}")
        return None


def _body_battery_points(raw_data: dict[str, Any]) -> list[list[Any]]:
    data = _safe_get(raw_data, "bodyBattery", "data", default=[])
    return data if isinstance(data, list) else []


def _fetch_body_battery(conn: sqlite3.Connection, date_str: str) -> dict[str, Any] | None:
    """Fetch Body Battery summary plus start/end values for the day."""
    try:
        row = _fetch_one(
            conn,
            """
            SELECT *
            FROM body_battery
            WHERE calendar_date = ?
            """,
            (date_str,),
        )
        if row is None:
            return None

        raw_data = _parse_json(_value_from_row(row, "raw_json"))
        points = _body_battery_points(raw_data)
        start_value = points[0][1] if points and len(points[0]) > 1 else None
        end_value = points[-1][1] if points and len(points[-1]) > 1 else None

        total_charged = _value_from_row(row, "charged")
        if total_charged is None:
            daily_row = _fetch_one(
                conn,
                """
                SELECT body_battery_charged
                FROM daily_summary
                WHERE calendar_date = ?
                """,
                (date_str,),
            )
            total_charged = _value_from_row(daily_row, "body_battery_charged")

        return {
            "total_charged": total_charged,
            "start": start_value,
            "end": end_value,
        }
    except Exception as exc:
        print(f"  ⚠ Garmin body battery error: {exc}")
        return None


def _fetch_training_readiness(conn: sqlite3.Connection, date_str: str) -> int | None:
    if not _table_exists(conn, "training_readiness"):
        return None

    try:
        row = _fetch_one(
            conn,
            """
            SELECT score
            FROM training_readiness
            WHERE calendar_date = ?
            """,
            (date_str,),
        )
        value = _value_from_row(row, "score")
        return int(value) if value is not None else None
    except Exception as exc:
        print(f"  ⚠ Garmin training readiness error: {exc}")
        return None


def _fetch_vo2max(conn: sqlite3.Connection, date_str: str) -> Any:
    """Fetch VO2 max from vo2max or fall back to user_profile raw JSON."""
    if _table_exists(conn, "vo2max"):
        try:
            row = _fetch_one(
                conn,
                """
                SELECT value
                FROM vo2max
                WHERE calendar_date = ?
                ORDER BY
                    CASE
                        WHEN sport = 'running' THEN 0
                        WHEN sport = 'cycling' THEN 1
                        ELSE 2
                    END,
                    value DESC
                LIMIT 1
                """,
                (date_str,),
            )
            value = _value_from_row(row, "value")
            if value is not None:
                return value
        except Exception as exc:
            print(f"  ⚠ Garmin VO2 max error: {exc}")

    if _table_exists(conn, "user_profile"):
        try:
            rows = _fetch_all(conn, "SELECT raw_json FROM user_profile")
            for row in rows:
                data = _parse_json(_value_from_row(row, "raw_json"))
                for key in ("vo2MaxRunning", "vo2MaxCycling", "vo2maxRunning", "vo2maxCycling"):
                    value = _safe_get(data, "userData", key)
                    if value is not None:
                        return value
        except Exception as exc:
            print(f"  ⚠ Garmin VO2 max fallback error: {exc}")

    return None


def _fetch_activities(conn: sqlite3.Connection, date_str: str) -> list[dict[str, Any]]:
    """Fetch activities for a local calendar date."""
    table_name = _first_existing_table(conn, "activities", "activity")
    if table_name is None:
        return []

    try:
        if table_name == "activity":
            rows = _fetch_all(
                conn,
                """
                SELECT activity_name, activity_type, duration_seconds, distance_meters, calories
                FROM activity
                WHERE substr(start_time_local, 1, 10) = ?
                ORDER BY start_time_local ASC
                """,
                (date_str,),
            )
            return [
                {
                    "name": _value_from_row(row, "activity_name"),
                    "activity_type": _value_from_row(row, "activity_type"),
                    "duration": _value_from_row(row, "duration_seconds"),
                    "distance": _value_from_row(row, "distance_meters"),
                    "calories": _value_from_row(row, "calories"),
                }
                for row in rows
            ]

        rows = _fetch_all(
            conn,
            """
            SELECT *
            FROM activities
            WHERE substr(start_time_local, 1, 10) = ?
            ORDER BY start_time_local ASC
            """,
            (date_str,),
        )
        return [
            {
                "name": _value_from_row(row, "name") or _value_from_row(row, "activity_name"),
                "activity_type": _value_from_row(row, "activity_type"),
                "duration": _value_from_row(row, "duration_seconds") or _value_from_row(row, "duration"),
                "distance": _value_from_row(row, "distance_meters") or _value_from_row(row, "distance"),
                "calories": _value_from_row(row, "calories"),
            }
            for row in rows
        ]
    except Exception as exc:
        print(f"  ⚠ Garmin activities error: {exc}")
        return []


def _fetch_garmin_day(conn: sqlite3.Connection, date_str: str) -> dict[str, Any]:
    return {
        "date": date_str,
        "stats": _fetch_stats(conn, date_str),
        "hrv": _fetch_hrv(conn, date_str),
        "sleep": _fetch_sleep(conn, date_str),
        "body_battery": _fetch_body_battery(conn, date_str),
        "training_readiness": _fetch_training_readiness(conn, date_str),
        "vo2max": _fetch_vo2max(conn, date_str),
        "activities": _fetch_activities(conn, date_str),
    }


def fetch_garmin_current() -> dict[str, Any] | None:
    """Fetch today's Garmin data from the local SQLite database."""
    conn = _connect()
    if conn is None:
        return None

    conn.row_factory = sqlite3.Row
    try:
        return _fetch_garmin_day(conn, date.today().isoformat())
    finally:
        conn.close()


def fetch_garmin_history(days: int = 30) -> list[dict[str, Any]]:
    """Fetch recent daily Garmin snapshots for the last `days` calendar days."""
    if days <= 0:
        return []

    conn = _connect()
    if conn is None:
        return []

    conn.row_factory = sqlite3.Row
    try:
        start_date = date.today() - timedelta(days=days - 1)
        history = []
        for offset in range(days):
            current_date = (start_date + timedelta(days=offset)).isoformat()
            history.append(_fetch_garmin_day(conn, current_date))
        return history
    finally:
        conn.close()


def get_schema() -> None:
    """Print all table names and their column names for debugging."""
    conn = _connect()
    if conn is None:
        return

    try:
        tables = _fetch_all(
            conn,
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """,
        )
        for table_row in tables:
            table_name = table_row[0]
            print(table_name)
            try:
                columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            except Exception as exc:
                print(f"  ⚠ schema error for {table_name}: {exc}")
                continue
            for column in columns:
                print(f"  - {column[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    print(json.dumps(fetch_garmin_current(), indent=2, default=str))
