#!/usr/bin/env python3
"""
Eight Sleep integration — fetches sleep data directly via Eight Sleep REST API.

Reads credentials from:
  /Users/rtbot/.openclaw/workspace/config/credentials.env
  (EIGHT_SLEEP_EMAIL, EIGHT_SLEEP_PASSWORD)

Returns None gracefully if credentials are missing or API fails.
"""

import asyncio
import os
import json
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

_CREDS_PATH = Path("/Users/rtbot/.openclaw/workspace/config/credentials.env")
AUTH_URL = "https://auth-api.8slp.net/v1/tokens"
API_BASE = "https://client-api.8slp.net/v1"
CLIENT_ID = "0894c7f33bb94800a03f1f4df13a4f38"
CLIENT_SECRET = "f0954a3ed5763ba3d06834c73731a32f15f168f47d4f164751275def86db0c76"
USER_ID = "cceaab04d3c143599ffcdf867d9d2b6b"


def _load_credentials():
    email = os.getenv("EIGHT_SLEEP_EMAIL")
    password = os.getenv("EIGHT_SLEEP_PASSWORD")
    if not email or not password:
        if _CREDS_PATH.exists():
            for line in _CREDS_PATH.read_text().splitlines():
                line = line.strip()
                if line.startswith("EIGHT_SLEEP_EMAIL="):
                    email = line.split("=", 1)[1].strip()
                elif line.startswith("EIGHT_SLEEP_PASSWORD="):
                    password = line.split("=", 1)[1].strip()
    return email, password


async def _async_fetch(email: str, password: str, date_str: str) -> dict | None:
    async with aiohttp.ClientSession() as session:
        # Step 1: OAuth2 login
        try:
            async with session.post(AUTH_URL, json={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "password",
                "username": email,
                "password": password,
            }) as r:
                if r.status != 200:
                    print(f"  ⚠ Eight Sleep: login failed ({r.status})")
                    return None
                data = await r.json()
                token = data["access_token"]
                user_id = USER_ID
        except Exception as e:
            print(f"  ⚠ Eight Sleep: login error — {e}")
            return None

        headers = {"Authorization": f"Bearer {token}"}

        # Step 2: Fetch sleep data for the date
        try:
            url = f"{API_BASE}/users/{user_id}/intervals"
            params = {"date": date_str}
            async with session.get(url, headers=headers, params=params) as r:
                if r.status != 200:
                    print(f"  ⚠ Eight Sleep: intervals fetch failed ({r.status})")
                    return None
                intervals_data = await r.json()
        except Exception as e:
            print(f"  ⚠ Eight Sleep: intervals error — {e}")
            return None

        intervals = intervals_data.get("intervals", [])
        if not intervals:
            print("  ⚠ Eight Sleep: no sleep intervals found for date")
            return None

        # Use the most recent interval (first in list = most recent)
        interval = intervals[0]
        stages = interval.get("stages", [])
        timeseries = interval.get("timeseries", {})

        # Calculate stage durations in seconds
        stage_durations = {"light": 0, "deep": 0, "rem": 0, "awake": 0, "out": 0}
        for stage in stages:
            s = stage.get("stage", "")
            dur = stage.get("duration", 0)
            if s in stage_durations:
                stage_durations[s] += dur

        total_sleep_s = sum(v for k, v in stage_durations.items() if k != "awake" and k != "out")

        # HRV — use rmssd (correct metric, matches Eight Sleep app display)
        hrv_vals = [v[1] for v in timeseries.get("rmssd", []) if v[1] is not None and v[1] > 0]
        hrv_avg = round(sum(hrv_vals) / len(hrv_vals), 1) if hrv_vals else None

        # Respiratory rate
        rr_vals = [v[1] for v in timeseries.get("respiratoryRate", []) if v[1] is not None and v[1] > 0]
        rr_avg = round(sum(rr_vals) / len(rr_vals), 1) if rr_vals else None

        # Heart rate
        hr_vals = [v[1] for v in timeseries.get("heartRate", []) if v[1] is not None and v[1] > 0]
        hr_avg = round(sum(hr_vals) / len(hr_vals), 1) if hr_vals else None

        # Bed temperature (left side, Celsius)
        temp_vals = [v[1] for v in timeseries.get("tempBedC", []) if v[1] is not None]
        if not temp_vals:
            # Try Fahrenheit and convert
            temp_f_vals = [v[1] for v in timeseries.get("tempBedF", []) if v[1] is not None]
            temp_vals = [round((f - 32) * 5 / 9, 1) for f in temp_f_vals] if temp_f_vals else []
        bed_temp = round(sum(temp_vals) / len(temp_vals), 1) if temp_vals else None

        # Sleep score — API returns 0 when not computed; treat 0 as None
        score = interval.get("score") or None

        result = {
            "sleep_score": score,
            "sleep_duration_s": total_sleep_s,
            "deep_sleep_s": stage_durations.get("deep"),
            "rem_sleep_s": stage_durations.get("rem"),
            "light_sleep_s": stage_durations.get("light"),
            "awake_s": stage_durations.get("awake"),
            "hrv": hrv_avg,
            "respiratory_rate": rr_avg,
            "heart_rate_avg": hr_avg,
            "bed_temp_c": bed_temp,
            "sleep_latency_s": None,
        }

        non_none = [v for v in result.values() if v is not None]
        if not non_none:
            print("  ⚠ Eight Sleep: connected but all values are None")
            return None

        return result


def fetch_eightsleep(date_str: str) -> dict | None:
    email, password = _load_credentials()
    if not email or not password:
        print("  ⚠ Eight Sleep: EIGHT_SLEEP_EMAIL / EIGHT_SLEEP_PASSWORD not set in credentials.env")
        return None
    try:
        return asyncio.run(_async_fetch(email, password, date_str))
    except Exception as e:
        print(f"  ⚠ Eight Sleep fetch failed: {e}")
        return None


if __name__ == "__main__":
    from datetime import date
    result = fetch_eightsleep(date.today().isoformat())
    print(json.dumps(result, indent=2, default=str))
