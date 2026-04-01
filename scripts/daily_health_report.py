#!/usr/bin/env python3
"""
Daily Health Report — pulls Oura Ring and Garmin Connect data,
computes a weighted overall score, prints a formatted console report,
and saves everything as JSON.

Usage:
    python daily_health_report.py              # today
    python daily_health_report.py 2026-03-24   # specific date
"""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OURA_BASE = "https://api.ouraring.com/v2/usercollection"
SEPARATOR = "━" * 37

# Load .env from same directory as this script
load_dotenv(SCRIPT_DIR / ".env")

OURA_TOKEN = os.getenv("OURA_ACCESS_TOKEN")
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_duration(seconds):
    """Convert seconds to a human-readable duration string like '7h 23m' or '45m'."""
    if seconds is None:
        return "N/A"
    total_minutes = int(seconds) // 60
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def safe_get(d, *keys, default=None):
    """Safely traverse nested dicts."""
    current = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
        if current is None:
            return default
    return current


def format_value(value, suffix="", fmt=None):
    """Format a value for display, returning 'N/A' if None."""
    if value is None:
        return "N/A"
    if fmt == "comma":
        return f"{int(value):,}{suffix}"
    if fmt == "plus":
        return f"+{value}{suffix}" if value >= 0 else f"{value}{suffix}"
    return f"{value}{suffix}"


# ---------------------------------------------------------------------------
# Oura API
# ---------------------------------------------------------------------------

def fetch_oura(date_str):
    """Fetch all relevant Oura data for a given date. Returns a dict or None."""
    if not OURA_TOKEN:
        return None

    headers = {"Authorization": f"Bearer {OURA_TOKEN}"}
    params = {"start_date": date_str, "end_date": date_str}
    result = {}

    endpoints = {
        "daily_sleep": "daily_sleep",
        "daily_readiness": "daily_readiness",
        "daily_activity": "daily_activity",
        "hrv": "hrv",
    }

    for key, endpoint in endpoints.items():
        try:
            resp = requests.get(
                f"{OURA_BASE}/{endpoint}",
                headers=headers,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data_list = resp.json().get("data", [])
            result[key] = data_list[0] if data_list else None
        except Exception as e:
            print(f"  ⚠ Oura {endpoint} error: {e}")
            result[key] = None

    # HRV endpoint returns a list of readings; compute average RMSSD
    if result.get("hrv") and isinstance(result["hrv"], dict):
        # Single-day HRV object may have nested samples
        pass  # keep as-is for raw storage
    # Also try fetching the HRV list for averaging
    try:
        resp = requests.get(
            f"{OURA_BASE}/hrv",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        hrv_list = resp.json().get("data", [])
        if hrv_list:
            rmssd_values = [
                item["rmssd"] for item in hrv_list
                if item.get("rmssd") is not None
            ]
            result["avg_rmssd"] = (
                round(sum(rmssd_values) / len(rmssd_values), 1)
                if rmssd_values else None
            )
        else:
            result["avg_rmssd"] = None
    except Exception:
        result["avg_rmssd"] = None

    return result


# ---------------------------------------------------------------------------
# Garmin API
# ---------------------------------------------------------------------------

def fetch_garmin(date_str):
    """Fetch all relevant Garmin Connect data for a given date. Returns a dict or None."""
    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        return None

    try:
        from garminconnect import Garmin
    except ImportError:
        print("  ⚠ garminconnect not installed. Run: pip install garminconnect")
        return None

    result = {}

    try:
        garmin = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        garmin.login()
    except Exception as e:
        print(f"  ⚠ Garmin login failed: {e}")
        print("    (If MFA is enabled, you may need to handle it manually.)")
        return None

    # Stats (steps, resting HR, stress)
    try:
        stats = garmin.get_stats(date_str)
        result["stats"] = {
            "totalSteps": safe_get(stats, "totalSteps"),
            "restingHeartRate": safe_get(stats, "restingHeartRate"),
            "averageStressLevel": safe_get(stats, "averageStressLevel"),
        }
    except Exception as e:
        print(f"  ⚠ Garmin stats error: {e}")
        result["stats"] = None

    # HRV data
    try:
        hrv = garmin.get_hrv_data(date_str)
        last_night = safe_get(hrv, "lastNight") or {}
        result["hrv"] = {
            "avgOvernightHrv": safe_get(last_night, "avgOvernightHrv"),
            "weeklyAvg": safe_get(hrv, "weeklyAvg"),
            "hrvStatus": safe_get(hrv, "hrvStatus"),
        }
    except Exception as e:
        print(f"  ⚠ Garmin HRV error: {e}")
        result["hrv"] = None

    # Body Battery
    try:
        bb_data = garmin.get_body_battery(date_str)
        if bb_data and isinstance(bb_data, list) and len(bb_data) > 0:
            total_charged = sum(
                item.get("charged", 0) for item in bb_data if isinstance(item, dict)
            )
            # Find start (first entry) and end (last entry) battery levels
            first = bb_data[0] if bb_data else {}
            last = bb_data[-1] if bb_data else {}
            result["body_battery"] = {
                "total_charged": total_charged,
                "start": safe_get(first, "batteryLevel") or safe_get(first, "charged"),
                "end": safe_get(last, "batteryLevel") or safe_get(last, "charged"),
            }
        else:
            result["body_battery"] = None
    except Exception as e:
        print(f"  ⚠ Garmin body battery error: {e}")
        result["body_battery"] = None

    # Training Readiness
    try:
        tr = garmin.get_training_readiness(date_str)
        result["training_readiness"] = safe_get(tr, "score")
    except Exception as e:
        print(f"  ⚠ Garmin training readiness error: {e}")
        result["training_readiness"] = None

    # Activities (recent 5, filter to target date)
    try:
        activities = garmin.get_activities(0, 5)
        day_activities = []
        for act in activities or []:
            act_date = str(safe_get(act, "startTimeLocal", default=""))[:10]
            if act_date == date_str:
                day_activities.append({
                    "name": safe_get(act, "activityName", default="Unknown"),
                    "duration": safe_get(act, "duration"),
                })
        result["activities"] = day_activities
    except Exception as e:
        print(f"  ⚠ Garmin activities error: {e}")
        result["activities"] = []

    return result


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_overall_score(sleep_score, readiness_score, training_readiness):
    """
    Compute weighted overall score.
    Weights: sleep 0.30, readiness 0.40, training_readiness 0.30.
    If a component is missing, redistribute its weight proportionally.
    """
    components = {
        "sleep": (sleep_score, 0.30),
        "readiness": (readiness_score, 0.40),
        "training": (training_readiness, 0.30),
    }

    available = {k: v for k, v in components.items() if v[0] is not None}
    if not available:
        return None, "Insufficient data for scoring."

    total_weight = sum(w for _, w in available.values())
    score = sum(val * (w / total_weight) for val, w in available.values())
    score = round(score)

    if score >= 85:
        advice = "Peak day. Push hard."
    elif score >= 70:
        advice = "Solid. Full training OK."
    elif score >= 55:
        advice = "Moderate. Lighter session recommended."
    else:
        advice = "Recovery day. Zone 2 only or rest."

    return score, advice


def is_oura_synced(oura):
    """Validate if Oura sleep/readiness data appears synced and meaningful for the day."""
    if not oura:
        return False

    daily_sleep = oura.get("daily_sleep")
    daily_readiness = oura.get("daily_readiness")

    sleep_score = safe_get(daily_sleep, "score")
    total_sleep_duration = safe_get(daily_sleep, "total_sleep_duration")
    readiness_score = safe_get(daily_readiness, "score")

    return (
        daily_sleep is not None
        and sleep_score is not None
        and total_sleep_duration is not None
        and total_sleep_duration > 0
        and daily_readiness is not None
        and readiness_score is not None
    )


# ---------------------------------------------------------------------------
# Report Printing
# ---------------------------------------------------------------------------

def print_report(date_str, oura, garmin, score, advice, oura_synced):
    """Print formatted console report."""
    print()
    print(SEPARATOR)
    print(f"🏃 DAILY HEALTH REPORT — {date_str}")
    print(SEPARATOR)
    if not oura_synced:
        print("⚠️ OURA DATA NOT YET SYNCED — sleep/readiness scores may be stale or missing. Open the Oura app to force sync.")

    # --- Sleep (Oura) ---
    print()
    sleep_header = "💤 SLEEP (Oura)"
    if not oura_synced:
        sleep_header += " ⚠️ NOT SYNCED"
    if oura and oura.get("daily_sleep"):
        sleep = oura["daily_sleep"]
        contributors = safe_get(sleep, "contributors") or {}
        print(sleep_header)
        sleep_score_display = format_value(safe_get(sleep, 'score'), '/100') if oura_synced else "N/A (not synced)"
        total_sleep_display = format_duration(safe_get(sleep, 'total_sleep_duration')) if oura_synced else "N/A (not synced)"
        print(f"  Score: {sleep_score_display}")
        print(f"  Total: {total_sleep_display}")
        deep = safe_get(contributors, "deep_sleep")
        rem = safe_get(contributors, "rem_sleep")
        print(f"  Deep: {format_value(deep, '%')}   REM: {format_value(rem, '%')}")
        eff = safe_get(contributors, "efficiency")
        lat = safe_get(contributors, "latency")
        lat_display = f"{lat} min" if lat is not None else "N/A"
        print(f"  Efficiency: {format_value(eff, '%')}   Latency: {lat_display}")
        avg_rmssd = oura.get("avg_rmssd")
        print(f"  Avg HRV (RMSSD): {format_value(avg_rmssd, ' ms')}")
    else:
        print(sleep_header)
        print("  (data unavailable - check credentials/token)")

    # --- Readiness (Oura) ---
    print()
    readiness_header = "📊 READINESS (Oura)"
    if not oura_synced:
        readiness_header += " ⚠️ NOT SYNCED"
    if oura and oura.get("daily_readiness"):
        readiness = oura["daily_readiness"]
        contributors = safe_get(readiness, "contributors") or {}
        print(readiness_header)
        readiness_score_display = format_value(safe_get(readiness, 'score'), '/100') if oura_synced else "N/A (not synced)"
        print(f"  Score: {readiness_score_display}")
        hrv_bal = safe_get(contributors, "hrv_balance")
        rhr = safe_get(readiness, "resting_heart_rate")
        print(f"  HRV Balance: {format_value(hrv_bal)}   Resting HR: {format_value(rhr, ' bpm')}")
        body_temp = safe_get(contributors, "body_temperature")
        if body_temp is not None:
            print(f"  Body Temp: {format_value(body_temp, '°C', fmt='plus')}")
        else:
            print(f"  Body Temp: N/A")
    else:
        print(readiness_header)
        print("  (data unavailable - check credentials/token)")

    # --- Energy (Garmin) ---
    print()
    if garmin:
        print("⚡ ENERGY (Garmin)")
        bb = garmin.get("body_battery")
        if bb:
            start = bb.get("start")
            end = bb.get("end")
            charged = bb.get("total_charged")
            if start is not None and end is not None:
                diff = (end or 0) - (start or 0)
                sign = "+" if diff >= 0 else ""
                print(f"  Body Battery: {start} → {end} ({sign}{diff})")
            else:
                print(f"  Body Battery: N/A")
        else:
            print(f"  Body Battery: N/A")

        tr = garmin.get("training_readiness")
        print(f"  Training Readiness: {format_value(tr, '/100')}")

        hrv = garmin.get("hrv") or {}
        status = hrv.get("hrvStatus", "N/A")
        weekly = hrv.get("weeklyAvg")
        if weekly is not None:
            print(f"  HRV Status: {status} (weekly avg: {weekly} ms)")
        else:
            print(f"  HRV Status: {format_value(status)}")

        stress = safe_get(garmin, "stats", "averageStressLevel")
        if stress is not None:
            if stress < 26:
                level = "low"
            elif stress < 51:
                level = "medium"
            elif stress < 76:
                level = "high"
            else:
                level = "very high"
            print(f"  Stress: {stress} ({level})")
        else:
            print(f"  Stress: N/A")
    else:
        print("⚡ ENERGY (Garmin)")
        print("  (data unavailable - check credentials/token)")

    # --- Activity ---
    print()
    print("🏋️ ACTIVITY")
    # Steps: prefer Garmin, fallback to Oura
    steps = None
    active_cal = None
    if garmin and garmin.get("stats"):
        steps = safe_get(garmin, "stats", "totalSteps")
    if oura and oura.get("daily_activity"):
        activity = oura["daily_activity"]
        if steps is None:
            steps = safe_get(activity, "steps")
        active_cal = safe_get(activity, "active_calories")
    print(f"  Steps: {format_value(steps, fmt='comma')}   Active Calories: {format_value(active_cal, fmt='comma')}")

    # Workouts from Garmin
    if garmin and garmin.get("activities"):
        for act in garmin["activities"]:
            name = act.get("name", "Unknown")
            dur = format_duration(act.get("duration"))
            print(f"  Today's workout: {name} — {dur}")
    elif not garmin:
        pass  # already showed unavailable above
    else:
        print("  No workouts recorded")

    # --- Overall Score ---
    print()
    if score is not None:
        print(f"🎯 OVERALL SCORE: {score}/100")
        print(f"  → {advice}")
    else:
        print(f"🎯 OVERALL SCORE: N/A")
        print(f"  → {advice}")
    print(SEPARATOR)
    print()


# ---------------------------------------------------------------------------
# JSON Save
# ---------------------------------------------------------------------------

def save_json(date_str, oura, garmin, score, advice, oura_synced):
    """Save all data to a JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "date": date_str,
        "oura": oura,
        "garmin": garmin,
        "computed": {
            "overall_score": score,
            "advice": advice,
            "oura_synced": oura_synced,
        },
    }
    filepath = DATA_DIR / f"{date_str}.json"
    with open(filepath, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"📁 Saved to {filepath}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Entry point: parse date, fetch data, compute score, print report, save JSON."""
    # Parse date argument
    if len(sys.argv) > 1:
        try:
            target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ Invalid date format: {sys.argv[1]}. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        target_date = date.today()

    date_str = target_date.isoformat()

    # Fetch data
    print(f"Fetching data for {date_str}...")
    oura = fetch_oura(date_str)
    garmin = fetch_garmin(date_str)

    oura_synced = is_oura_synced(oura)

    # Extract scores for overall computation
    sleep_score = safe_get(oura, "daily_sleep", "score") if oura else None
    readiness_score = safe_get(oura, "daily_readiness", "score") if oura else None
    training_readiness = safe_get(garmin, "training_readiness") if garmin else None

    score, advice = compute_overall_score(sleep_score, readiness_score, training_readiness)

    # Output
    print_report(date_str, oura, garmin, score, advice, oura_synced)
    save_json(date_str, oura, garmin, score, advice, oura_synced)


if __name__ == "__main__":
    main()
