#!/usr/bin/env python3
"""
Alfred Health Dashboard — Flask server
Serves the dashboard UI and provides API endpoints.

Usage: python server.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
SCRIPTS_DIR = PROJECT_DIR / "scripts"
GARMIN_DB_PATH = Path("/Users/rtbot/.garmin-givemydata/garmin.db")

app = Flask(__name__, static_folder=str(BASE_DIR))


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(GARMIN_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def safe_json_loads(raw_json: Any) -> dict[str, Any]:
    if not raw_json:
        return {}
    try:
        return json.loads(raw_json)
    except (TypeError, json.JSONDecodeError):
        return {}


def nested_get(data: Any, *path: str) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def daterange_strings(start_date: date, end_date: date) -> list[str]:
    days = (end_date - start_date).days
    return [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range(days + 1)
    ]


def extract_sleep_score(raw_json: Any) -> int | None:
    payload = safe_json_loads(raw_json)
    value = nested_get(payload, "dailySleepDTO", "sleepScores", "overall", "value")
    return int(value) if value is not None else None


def compute_garmin_sleep_efficiency(row: sqlite3.Row, raw_json: Any) -> float | None:
    payload = safe_json_loads(raw_json)
    sleep_seconds = row["sleep_time_seconds"]
    awake_seconds = row["awake_sleep_seconds"]
    unmeasurable = row["unmeasurable_sleep_seconds"]

    time_in_bed = nested_get(payload, "dailySleepDTO", "timeInBedSeconds")
    if time_in_bed is None:
        parts = [sleep_seconds, awake_seconds, unmeasurable]
        if any(part is not None for part in parts):
            time_in_bed = sum(part or 0 for part in parts)

    if not time_in_bed or not sleep_seconds:
        return None
    return round((sleep_seconds / time_in_bed) * 100, 1)


def load_saved_records() -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for path in sorted(DATA_DIR.glob("????-??-??.json")):
        try:
            with path.open() as handle:
                records.append(json.load(handle))
        except Exception:
            continue
    return records


def build_recent_garmin_rows(days: int = 30) -> list[dict[str, Any]]:
    days = max(1, min(days, 3650))
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                ds.calendar_date,
                ds.total_steps,
                ds.active_kilocalories,
                ds.resting_heart_rate,
                ds.average_stress_level,
                ds.body_battery_highest,
                ds.moderate_intensity_minutes,
                ds.vigorous_intensity_minutes,
                sl.sleep_time_seconds,
                sl.deep_sleep_seconds,
                sl.rem_sleep_seconds,
                sl.light_sleep_seconds,
                sl.awake_sleep_seconds,
                sl.unmeasurable_sleep_seconds,
                sl.raw_json AS sleep_raw_json,
                h.last_night_avg,
                h.weekly_avg,
                h.status AS hrv_status,
                tr.score AS training_readiness
            FROM daily_summary ds
            LEFT JOIN sleep sl ON sl.calendar_date = ds.calendar_date
            LEFT JOIN hrv h ON h.calendar_date = ds.calendar_date
            LEFT JOIN training_readiness tr ON tr.calendar_date = ds.calendar_date
            WHERE ds.calendar_date BETWEEN ? AND ?
            ORDER BY ds.calendar_date ASC
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()

    row_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_map[row["calendar_date"]] = {
            "date": row["calendar_date"],
            "steps": row["total_steps"],
            "active_calories": row["active_kilocalories"],
            "resting_heart_rate": row["resting_heart_rate"],
            "stress_level": row["average_stress_level"],
            "hrv_overnight": row["last_night_avg"],
            "hrv_weekly_avg": row["weekly_avg"],
            "hrv_status": row["hrv_status"],
            "sleep_score": extract_sleep_score(row["sleep_raw_json"]),
            "sleep_time_seconds": row["sleep_time_seconds"],
            "deep_sleep_seconds": row["deep_sleep_seconds"],
            "rem_sleep_seconds": row["rem_sleep_seconds"],
            "light_sleep_seconds": row["light_sleep_seconds"],
            "sleep_efficiency": compute_garmin_sleep_efficiency(row, row["sleep_raw_json"]),
            "body_battery_max": row["body_battery_highest"],
            "moderate_intensity_minutes": row["moderate_intensity_minutes"] or 0,
            "vigorous_intensity_minutes": row["vigorous_intensity_minutes"] or 0,
            "training_readiness": row["training_readiness"],
        }

    return [
        row_map.get(
            day_str,
            {
                "date": day_str,
                "steps": None,
                "active_calories": None,
                "resting_heart_rate": None,
                "stress_level": None,
                "hrv_overnight": None,
                "hrv_weekly_avg": None,
                "hrv_status": None,
                "sleep_score": None,
                "sleep_time_seconds": None,
                "deep_sleep_seconds": None,
                "rem_sleep_seconds": None,
                "light_sleep_seconds": None,
                "sleep_efficiency": None,
                "body_battery_max": None,
                "moderate_intensity_minutes": 0,
                "vigorous_intensity_minutes": 0,
                "training_readiness": None,
            },
        )
        for day_str in daterange_strings(start_date, end_date)
    ]


def build_recent_garmin_activities(days: int = 30) -> list[dict[str, Any]]:
    days = max(1, min(days, 3650))
    start_date = (date.today() - timedelta(days=days - 1)).isoformat()

    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT activity_name, activity_type, start_time_local, duration_seconds, calories
            FROM activity
            WHERE substr(start_time_local, 1, 10) >= ?
            ORDER BY start_time_local DESC
            """,
            (start_date,),
        ).fetchall()

    return [
        {
            "date": (row["start_time_local"] or "")[:10] or None,
            "activity_type": row["activity_type"],
            "activity_name": row["activity_name"],
            "duration_seconds": row["duration_seconds"],
            "calories": row["calories"],
        }
        for row in rows
    ]


def build_longterm_rows(bucket_days: int = 15) -> dict[str, Any]:
    bucket_days = max(7, min(bucket_days, 60))

    with get_db_connection() as conn:
        daily_rows = conn.execute(
            """
            SELECT
                ds.calendar_date,
                ds.resting_heart_rate,
                sl.raw_json AS sleep_raw_json,
                h.last_night_avg
            FROM daily_summary ds
            LEFT JOIN sleep sl ON sl.calendar_date = ds.calendar_date
            LEFT JOIN hrv h ON h.calendar_date = ds.calendar_date
            WHERE ds.calendar_date IS NOT NULL
            ORDER BY ds.calendar_date ASC
            """
        ).fetchall()

    if not daily_rows:
        return {
            "rows": [],
            "message": "Insufficient historical data — charts will populate over time",
        }

    base_date = datetime.strptime(daily_rows[0]["calendar_date"], "%Y-%m-%d").date()
    buckets: dict[int, dict[str, Any]] = {}

    def get_bucket(day_str: str) -> dict[str, Any]:
        current_day = datetime.strptime(day_str, "%Y-%m-%d").date()
        bucket_index = (current_day - base_date).days // bucket_days
        bucket = buckets.setdefault(
            bucket_index,
            {
                "period_start": day_str,
                "period_end": day_str,
                "resting_sum": 0.0,
                "resting_count": 0,
                "sleep_sum": 0.0,
                "sleep_count": 0,
                "hrv_sum": 0.0,
                "hrv_count": 0,
            },
        )
        bucket["period_start"] = min(bucket["period_start"], day_str)
        bucket["period_end"] = max(bucket["period_end"], day_str)
        return bucket

    for row in daily_rows:
        bucket = get_bucket(row["calendar_date"])

        if row["resting_heart_rate"] is not None:
            bucket["resting_sum"] += row["resting_heart_rate"]
            bucket["resting_count"] += 1

        sleep_score = extract_sleep_score(row["sleep_raw_json"])
        if sleep_score is not None:
            bucket["sleep_sum"] += sleep_score
            bucket["sleep_count"] += 1

        if row["last_night_avg"] is not None:
            bucket["hrv_sum"] += row["last_night_avg"]
            bucket["hrv_count"] += 1

    results = []
    for bucket_index in sorted(buckets):
        bucket = buckets[bucket_index]
        start_label = datetime.strptime(bucket["period_start"], "%Y-%m-%d").strftime("%b %Y")
        results.append(
            {
                "bucket_index": bucket_index,
                "period_start": bucket["period_start"],
                "period_end": bucket["period_end"],
                "period_label": start_label,
                "avg_resting_hr": (
                    round(bucket["resting_sum"] / bucket["resting_count"], 2)
                    if bucket["resting_count"]
                    else None
                ),
                "avg_sleep_score": (
                    round(bucket["sleep_sum"] / bucket["sleep_count"], 2)
                    if bucket["sleep_count"]
                    else None
                ),
                "avg_hrv_overnight": (
                    round(bucket["hrv_sum"] / bucket["hrv_count"], 2)
                    if bucket["hrv_count"]
                    else None
                ),
            }
        )

    has_any_data = any(
        row["avg_resting_hr"] is not None
        or row["avg_sleep_score"] is not None
        or row["avg_hrv_overnight"] is not None
        for row in results
    )
    return {
        "rows": results,
        "message": None if has_any_data else "Insufficient historical data — charts will populate over time",
    }


def build_insight_summary(days: int = 30) -> dict[str, Any]:
    rows = build_recent_garmin_rows(days=days)

    def metric_stats(key: str) -> dict[str, Any] | None:
        values = [row[key] for row in rows if row.get(key) is not None]
        if not values:
            return None
        return {
            "avg": round(sum(values) / len(values), 2),
            "min": min(values),
            "max": max(values),
        }

    best_sleep_day = max(
        (row for row in rows if row.get("sleep_score") is not None),
        key=lambda row: row["sleep_score"],
        default=None,
    )
    lowest_hrv_day = min(
        (row for row in rows if row.get("hrv_overnight") is not None),
        key=lambda row: row["hrv_overnight"],
        default=None,
    )
    highest_intensity_day = max(
        rows,
        key=lambda row: (row.get("moderate_intensity_minutes") or 0) + (row.get("vigorous_intensity_minutes") or 0),
        default=None,
    )

    notable_events: list[str] = []
    if best_sleep_day:
        notable_events.append(
            f"Best sleep score was {best_sleep_day['sleep_score']} on {best_sleep_day['date']}."
        )
    if lowest_hrv_day:
        notable_events.append(
            f"Lowest overnight HRV was {lowest_hrv_day['hrv_overnight']} ms on {lowest_hrv_day['date']}."
        )
    if highest_intensity_day:
        total_intensity = (
            (highest_intensity_day.get("moderate_intensity_minutes") or 0)
            + (highest_intensity_day.get("vigorous_intensity_minutes") or 0)
        )
        notable_events.append(
            f"Highest intensity day was {highest_intensity_day['date']} with {total_intensity} total minutes."
        )

    return {
        "period_days": days,
        "generated_from": {
            "start_date": rows[0]["date"] if rows else None,
            "end_date": rows[-1]["date"] if rows else None,
        },
        "metrics": {
            "resting_heart_rate": metric_stats("resting_heart_rate"),
            "hrv_overnight": metric_stats("hrv_overnight"),
            "sleep_score": metric_stats("sleep_score"),
            "body_battery_max": metric_stats("body_battery_max"),
        },
        "daily_data": rows,
        "notable_events": notable_events,
    }


@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR), "index.html")


@app.route("/api/data")
def get_data():
    return jsonify(load_saved_records())


@app.route("/api/today")
def get_today():
    today = date.today().isoformat()
    output_file = DATA_DIR / f"{today}.json"

    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "daily_health_report.py"), today],
            capture_output=True,
            text=True,
            timeout=90,
            env={**os.environ, "PYTHONPATH": str(SCRIPTS_DIR)},
        )
        if output_file.exists():
            with output_file.open() as handle:
                data = json.load(handle)
            data["_stdout"] = result.stdout
            return jsonify(data)
        return jsonify(
            {
                "error": "No data generated",
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        ), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Fetch timed out"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/withings/history")
def withings_history():
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from withings_fetcher import fetch_withings_history

        history = fetch_withings_history(days=90)
        return jsonify(history)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/garmin/trends")
def garmin_trends():
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        return jsonify({"error": "days must be an integer"}), 400

    try:
        return jsonify(build_recent_garmin_rows(days=days))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/garmin/activities")
def garmin_activities_endpoint():
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        return jsonify({"error": "days must be an integer"}), 400

    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from garmin_fetcher import fetch_garmin_history

        history = fetch_garmin_history(days=days)
        activities = []
        for day in history:
            for act in (day.get("activities") or []):
                activities.append(
                    {
                        "date": day["date"],
                        "name": act.get("name"),
                        "activity_type": act.get("activity_type"),
                        "duration_seconds": act.get("duration"),
                        "distance_meters": act.get("distance"),
                        "calories": act.get("calories"),
                    }
                )
        return jsonify(activities)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/garmin/longterm")
def garmin_longterm():
    try:
        bucket_days = int(request.args.get("bucket_days", 15))
    except ValueError:
        return jsonify({"error": "bucket_days must be an integer"}), 400

    try:
        payload = build_longterm_rows(bucket_days=bucket_days)
        if not payload.get("rows"):
            return jsonify(
                {
                    "rows": [],
                    "message": "Insufficient historical data — charts will populate over time",
                }
            )
        return jsonify(payload)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/eightsleep/history")
def eightsleep_history():
    import time as _time

    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        return jsonify({"error": "days must be an integer"}), 400

    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from eightsleep_fetcher import fetch_eightsleep
        from datetime import date as _date, timedelta

        results = []
        for offset in range(days - 1, -1, -1):
            d = (_date.today() - timedelta(days=offset)).isoformat()
            data = fetch_eightsleep(d)
            entry = {"date": d}
            if data:
                entry.update(data)
            results.append(entry)
            _time.sleep(0.3)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/insights", methods=["POST"])
def insights():
    try:
        summary = build_insight_summary(days=30)
        generated_at = datetime.now().isoformat(timespec="seconds")
        prompt = (
            "You are a sports medicine doctor and health data analyst. "
            "Analyze this 30-day health summary for a 52-year-old male athlete "
            "(beach volleyball 3x/week, home gym, triathlete background). "
            "Identify trends, correlations between metrics, and give 3 specific actionable "
            "recommendations. Be direct and concise. Data: "
            f"{json.dumps(summary, separators=(',', ':'))}"
        )

        payload = json.dumps(
            {
                "model": "gemma3:27b",
                "stream": False,
                "prompt": prompt,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))

        return jsonify(
            {
                "insights": body.get("response"),
                "generated_at": generated_at,
            }
        )
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return jsonify(
            {
                "insights": "AI insights require Ollama running locally. Start with: ollama serve",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "error": "ollama_offline",
            }
        ), 200
    except Exception as exc:
        return jsonify(
            {
                "insights": None,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "error": str(exc),
            }
        ), 500


if __name__ == "__main__":
    print("🏃 Alfred Health Dashboard")
    print("   Running at http://localhost:8888")
    print(f"   Data dir: {DATA_DIR}")
    app.run(host="0.0.0.0", port=8888, debug=False)
