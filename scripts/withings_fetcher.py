#!/usr/bin/env python3
"""
Withings integration — fetches weight and body composition data.
Handles OAuth token refresh automatically.
"""

import json
import os
import time
from pathlib import Path

import requests

TOKENS_PATH = Path("/Users/rtbot/.openclaw/workspace/config/withings_tokens.json")
WITHINGS_API = "https://wbsapi.withings.net"
WITHINGS_OAUTH = "https://wbsapi.withings.net/v2/oauth2"

# Measure type codes
MEASURE_TYPES = {
    1: "weight_kg",
    6: "fat_ratio_pct",
    8: "fat_mass_kg",
    76: "muscle_mass_kg",
    77: "hydration_kg",
    88: "bone_mass_kg",
    5: "fat_free_mass_kg",
}


def _load_tokens():
    if not TOKENS_PATH.exists():
        return None
    with open(TOKENS_PATH) as f:
        return json.load(f)


def _save_tokens(tokens):
    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKENS_PATH, "w") as f:
        json.dump(tokens, f, indent=2)


def _refresh_token(tokens):
    """Refresh access token using refresh_token."""
    creds_path = Path("/Users/rtbot/.openclaw/workspace/config/credentials.env")
    client_id = None
    client_secret = None

    if creds_path.exists():
        for line in creds_path.read_text().splitlines():
            if line.startswith("WITHINGS_CLIENT_ID="):
                client_id = line.split("=", 1)[1].strip()
            elif line.startswith("WITHINGS_CLIENT_SECRET="):
                client_secret = line.split("=", 1)[1].strip()

    if not client_id or not client_secret:
        print("  ⚠ Withings client_id/secret not found in credentials.env")
        return None

    resp = requests.post(WITHINGS_OAUTH, data={
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tokens.get("refresh_token"),
    }, timeout=15)

    data = resp.json()
    if data.get("status") != 0:
        print(f"  ⚠ Withings token refresh failed: {data}")
        return None

    new_tokens = data["body"]
    _save_tokens(new_tokens)
    return new_tokens


def _get_valid_token():
    """Load tokens, refresh if expired, return access_token or None."""
    tokens = _load_tokens()
    if not tokens:
        return None

    # Check expiry (withings tokens expire after 3 hours)
    expires_in = tokens.get("expires_in", 0)
    created_at = tokens.get("created", int(time.time()))
    # If no created field, try to refresh proactively
    if int(time.time()) > created_at + expires_in - 300:
        tokens = _refresh_token(tokens)
        if not tokens:
            return None

    return tokens.get("access_token")


def fetch_withings(date_str=None):
    """
    Fetch latest body measurements from Withings.
    date_str: optional YYYY-MM-DD string. If None, fetches last 30 days.
    Returns dict with weight_kg, fat_ratio_pct, fat_mass_kg, muscle_mass_kg, etc.
    """
    access_token = _get_valid_token()
    if not access_token:
        print("  ⚠ Withings: no valid access token")
        return None

    # Build date range
    if date_str:
        from datetime import datetime, timedelta
        end_dt = datetime.strptime(date_str, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=1)
        params = {
            "action": "getmeas",
            "meastypes": ",".join(str(k) for k in MEASURE_TYPES.keys()),
            "category": 1,
            "startdate": int(start_dt.timestamp()),
            "enddate": int((end_dt + timedelta(days=1)).timestamp()),
        }
    else:
        from datetime import datetime, timedelta
        params = {
            "action": "getmeas",
            "meastypes": ",".join(str(k) for k in MEASURE_TYPES.keys()),
            "category": 1,
            "lastupdate": int((datetime.now() - timedelta(days=30)).timestamp()),
        }

    try:
        resp = requests.get(
            f"{WITHINGS_API}/measure",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15,
        )
        data = resp.json()

        if data.get("status") != 0:
            # Token may have expired, try refresh
            tokens = _load_tokens()
            new_tokens = _refresh_token(tokens) if tokens else None
            if not new_tokens:
                print(f"  ⚠ Withings API error: {data.get('error', 'unknown')}")
                return None
            access_token = new_tokens.get("access_token")
            resp = requests.get(
                f"{WITHINGS_API}/measure",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=15,
            )
            data = resp.json()

        if data.get("status") != 0:
            print(f"  ⚠ Withings API error after refresh: {data}")
            return None

        measuregrps = data.get("body", {}).get("measuregrps", [])
        if not measuregrps:
            return None

        # Take the most recent measurement group
        latest = sorted(measuregrps, key=lambda x: x.get("date", 0), reverse=True)[0]
        result = {}
        for measure in latest.get("measures", []):
            mtype = measure.get("type")
            value = measure.get("value", 0)
            unit = measure.get("unit", 0)
            real_value = round(value * (10 ** unit), 2)
            key = MEASURE_TYPES.get(mtype)
            if key:
                result[key] = real_value

        result["measured_at"] = latest.get("date")
        return result if result else None

    except Exception as e:
        print(f"  ⚠ Withings fetch error: {e}")
        return None


def fetch_withings_history(days=30):
    """
    Fetch weight history for the last N days.
    Returns list of {date, weight_kg, fat_ratio_pct, muscle_mass_kg} sorted by date.
    """
    access_token = _get_valid_token()
    if not access_token:
        return []

    from datetime import datetime, timedelta
    params = {
        "action": "getmeas",
        "meastypes": "1,6,76",  # weight, fat%, muscle
        "category": 1,
        "lastupdate": int((datetime.now() - timedelta(days=days)).timestamp()),
    }

    try:
        resp = requests.get(
            f"{WITHINGS_API}/measure",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15,
        )
        data = resp.json()
        if data.get("status") != 0:
            return []

        history = []
        for grp in data.get("body", {}).get("measuregrps", []):
            entry = {"date": datetime.fromtimestamp(grp["date"]).strftime("%Y-%m-%d")}
            for m in grp.get("measures", []):
                value = round(m["value"] * (10 ** m["unit"]), 2)
                key = MEASURE_TYPES.get(m["type"])
                if key:
                    entry[key] = value
            if "weight_kg" in entry:
                history.append(entry)

        return sorted(history, key=lambda x: x["date"])

    except Exception as e:
        print(f"  ⚠ Withings history error: {e}")
        return []


if __name__ == "__main__":
    from datetime import date
    result = fetch_withings(date.today().isoformat())
    print(json.dumps(result, indent=2))
