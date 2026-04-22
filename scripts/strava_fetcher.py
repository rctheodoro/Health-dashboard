#!/usr/bin/env python3
"""
Strava integration for the Alfred Health Dashboard.

Reads credentials from the shared credentials.env, refreshes tokens when
required, and fetches recent athlete activities.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
CREDENTIALS_PATH = Path("/Users/rtbot/.openclaw/workspace/config/credentials.env")
TOKEN_CACHE_PATH = PROJECT_DIR / "data" / "strava_tokens.json"
STRAVA_API = "https://www.strava.com/api/v3"
STRAVA_OAUTH = "https://www.strava.com/oauth/token"
TOKEN_REFRESH_BUFFER_S = 300


class StravaError(Exception):
    """Base error for Strava integration issues."""


class StravaRateLimitError(StravaError):
    """Raised when Strava rejects or nears a rate limit."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class StravaCredentials:
    client_id: str
    client_secret: str
    access_token: str | None
    refresh_token: str | None
    expires_at: int | None = None


def _parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _load_cache() -> dict[str, Any]:
    if not TOKEN_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(TOKEN_CACHE_PATH.read_text())
    except Exception:
        return {}


def _save_cache(payload: dict[str, Any]) -> None:
    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def _load_credentials() -> StravaCredentials:
    env = _parse_env_file(CREDENTIALS_PATH)
    cache = _load_cache()

    client_id = env.get("STRAVA_CLIENT_ID")
    client_secret = env.get("STRAVA_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise StravaError("Strava client credentials not found in credentials.env")

    access_token = cache.get("access_token") or env.get("STRAVA_ACCESS_TOKEN")
    refresh_token = cache.get("refresh_token") or env.get("STRAVA_REFRESH_TOKEN")
    expires_at_raw = cache.get("expires_at") or env.get("STRAVA_ACCESS_TOKEN_EXPIRES_AT")

    expires_at: int | None = None
    if expires_at_raw not in (None, ""):
        try:
            expires_at = int(expires_at_raw)
        except (TypeError, ValueError):
            expires_at = None

    return StravaCredentials(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


def _write_credentials_update(tokens: dict[str, Any]) -> None:
    env = _parse_env_file(CREDENTIALS_PATH)
    env["STRAVA_ACCESS_TOKEN"] = tokens["access_token"]
    env["STRAVA_REFRESH_TOKEN"] = tokens["refresh_token"]
    env["STRAVA_ACCESS_TOKEN_EXPIRES_AT"] = str(tokens["expires_at"])

    if CREDENTIALS_PATH.exists():
        lines = CREDENTIALS_PATH.read_text().splitlines()
    else:
        lines = []

    seen: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            new_lines.append(line)
            continue

        key, _ = line.split("=", 1)
        key = key.strip()
        if key in (
            "STRAVA_ACCESS_TOKEN",
            "STRAVA_REFRESH_TOKEN",
            "STRAVA_ACCESS_TOKEN_EXPIRES_AT",
        ):
            new_lines.append(f"{key}={env[key]}")
            seen.add(key)
        else:
            new_lines.append(line)

    for key in (
        "STRAVA_ACCESS_TOKEN",
        "STRAVA_REFRESH_TOKEN",
        "STRAVA_ACCESS_TOKEN_EXPIRES_AT",
    ):
        if key not in seen:
            new_lines.append(f"{key}={env[key]}")

    try:
        CREDENTIALS_PATH.write_text("\n".join(new_lines).rstrip() + "\n")
    except PermissionError:
        # Sandbox fallback so refreshed tokens still survive within this project.
        _save_cache(
            {
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "expires_at": tokens["expires_at"],
                "updated_at": int(time.time()),
            }
        )
    else:
        _save_cache(
            {
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "expires_at": tokens["expires_at"],
                "updated_at": int(time.time()),
            }
        )


def _refresh_access_token(credentials: StravaCredentials) -> StravaCredentials:
    if not credentials.refresh_token:
        raise StravaError("Strava refresh token not configured")

    response = requests.post(
        STRAVA_OAUTH,
        data={
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": credentials.refresh_token,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()

    updated = {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", credentials.refresh_token),
        "expires_at": int(payload["expires_at"]),
    }
    _write_credentials_update(updated)

    credentials.access_token = updated["access_token"]
    credentials.refresh_token = updated["refresh_token"]
    credentials.expires_at = updated["expires_at"]
    return credentials


def _token_is_expired(credentials: StravaCredentials) -> bool:
    if not credentials.access_token:
        return True
    if credentials.expires_at is None:
        return False
    return time.time() >= credentials.expires_at - TOKEN_REFRESH_BUFFER_S


def _parse_rate_limit(headers: requests.structures.CaseInsensitiveDict[str]) -> tuple[list[int] | None, list[int] | None]:
    def _split_header(name: str) -> list[int] | None:
        raw = headers.get(name)
        if not raw:
            return None
        try:
            return [int(part.strip()) for part in raw.split(",")]
        except ValueError:
            return None

    return _split_header("X-RateLimit-Limit"), _split_header("X-RateLimit-Usage")


def _check_rate_limits(response: requests.Response) -> None:
    limits, usage = _parse_rate_limit(response.headers)
    if response.status_code == 429:
        retry_after = None
        raw_retry = response.headers.get("Retry-After")
        if raw_retry:
            try:
                retry_after = int(raw_retry)
            except ValueError:
                retry_after = None
        raise StravaRateLimitError("Strava rate limit reached", retry_after=retry_after)

    if not limits or not usage or len(limits) < 2 or len(usage) < 2:
        return

    short_limit, daily_limit = limits[0], limits[1]
    short_usage, daily_usage = usage[0], usage[1]

    if short_limit and short_usage >= short_limit:
        raise StravaRateLimitError("Strava 15-minute rate limit reached")
    if daily_limit and daily_usage >= daily_limit:
        raise StravaRateLimitError("Strava daily rate limit reached")


def _request_activities(
    credentials: StravaCredentials,
    after_epoch: int,
    page: int,
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{STRAVA_API}/athlete/activities",
        headers={"Authorization": f"Bearer {credentials.access_token}"},
        params={"after": after_epoch, "page": page, "per_page": 100},
        timeout=20,
    )

    if response.status_code == 401:
        credentials = _refresh_access_token(credentials)
        response = requests.get(
            f"{STRAVA_API}/athlete/activities",
            headers={"Authorization": f"Bearer {credentials.access_token}"},
            params={"after": after_epoch, "page": page, "per_page": 100},
            timeout=20,
        )

    _check_rate_limits(response)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _to_minutes(seconds: Any) -> float | None:
    if seconds is None:
        return None
    try:
        return round(float(seconds) / 60, 1)
    except (TypeError, ValueError):
        return None


def _to_km(meters: Any) -> float | None:
    if meters is None:
        return None
    try:
        return round(float(meters) / 1000, 2)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any, decimals: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


def _normalize_activity(activity: dict[str, Any]) -> dict[str, Any]:
    start_date_local = activity.get("start_date_local") or activity.get("start_date")
    parsed_date = None
    if start_date_local:
        try:
            parsed_date = datetime.fromisoformat(start_date_local.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            parsed_date = str(start_date_local)[:10]

    return {
        "date": parsed_date,
        "name": activity.get("name") or "Untitled activity",
        "sport_type": activity.get("sport_type") or activity.get("type") or "Workout",
        "distance_km": _to_km(activity.get("distance")),
        "duration_min": _to_minutes(activity.get("moving_time") or activity.get("elapsed_time")),
        "elevation_gain": _to_float(activity.get("total_elevation_gain"), 0),
        "average_hr": _to_float(activity.get("average_heartrate"), 0),
        "max_hr": _to_float(activity.get("max_heartrate"), 0),
        "calories": _to_float(activity.get("calories"), 0),
    }


def fetch_recent_activities(days: int = 30) -> list[dict[str, Any]]:
    """Return normalized Strava activities from the last `days` days."""
    credentials = _load_credentials()
    if _token_is_expired(credentials):
        credentials = _refresh_access_token(credentials)

    after_dt = datetime.now(timezone.utc) - timedelta(days=days)
    after_epoch = int(after_dt.timestamp())

    activities: list[dict[str, Any]] = []
    page = 1

    while True:
        page_items = _request_activities(credentials, after_epoch, page)
        if not page_items:
            break
        activities.extend(_normalize_activity(item) for item in page_items)
        if len(page_items) < 100:
            break
        page += 1

    activities.sort(key=lambda item: item.get("date") or "", reverse=True)
    return activities


if __name__ == "__main__":
    print(json.dumps(fetch_recent_activities(days=30), indent=2))
