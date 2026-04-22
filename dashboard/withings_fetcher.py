#!/usr/bin/env python3
"""
Dashboard-local Withings history loader.

Prefers saved JSON snapshots under scripts/data/ when available, then falls back
to project-level data/ snapshots. If a live Withings integration exists in the
scripts directory, it is used only as a best-effort fallback and failures are
silently ignored.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
SCRIPT_DATA_DIR = PROJECT_DIR / "scripts" / "data"
DATA_DIR = PROJECT_DIR / "data"
SCRIPTS_FETCHER_PATH = PROJECT_DIR / "scripts" / "withings_fetcher.py"

OUTPUT_FIELDS = (
    "date",
    "weight_kg",
    "fat_ratio_pct",
    "fat_mass_kg",
    "muscle_mass_kg",
)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_entry(day: str, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None

    weight_kg = _coerce_float(payload.get("weight_kg"))
    fat_ratio_pct = _coerce_float(payload.get("fat_ratio_pct"))
    fat_mass_kg = _coerce_float(payload.get("fat_mass_kg"))
    muscle_mass_kg = _coerce_float(payload.get("muscle_mass_kg"))

    if all(value is None for value in (weight_kg, fat_ratio_pct, fat_mass_kg, muscle_mass_kg)):
        return None

    return {
        "date": day,
        "weight_kg": weight_kg,
        "fat_ratio_pct": fat_ratio_pct,
        "fat_mass_kg": fat_mass_kg,
        "muscle_mass_kg": muscle_mass_kg,
    }


def _iter_snapshot_dirs() -> list[Path]:
    dirs: list[Path] = []
    for directory in (SCRIPT_DATA_DIR, DATA_DIR):
        if directory.exists():
            dirs.append(directory)
    return dirs


def _load_history_from_snapshots(days: int) -> list[dict[str, Any]]:
    cutoff = date.today() - timedelta(days=max(days, 1) - 1)
    rows_by_date: dict[str, dict[str, Any]] = {}

    for directory in _iter_snapshot_dirs():
        for path in sorted(directory.glob("*.json")):
            if path.name == "strava_tokens.json":
                continue

            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue

            if not isinstance(payload, dict):
                continue

            day = payload.get("date")
            if not isinstance(day, str):
                continue

            try:
                day_value = date.fromisoformat(day)
            except ValueError:
                continue

            if day_value < cutoff:
                continue

            entry = _normalize_entry(day, payload.get("withings"))
            if entry:
                rows_by_date[day] = entry

    return [rows_by_date[day] for day in sorted(rows_by_date)]


def _load_live_history(days: int) -> list[dict[str, Any]]:
    if not SCRIPTS_FETCHER_PATH.exists():
        return []

    try:
        spec = importlib.util.spec_from_file_location("_scripts_withings_fetcher", SCRIPTS_FETCHER_PATH)
        if spec is None or spec.loader is None:
            return []
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fetcher = getattr(module, "fetch_withings_history", None)
        if not callable(fetcher):
            return []
        rows = fetcher(days=days)
    except Exception:
        return []

    if not isinstance(rows, list):
        return []

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = row.get("date")
        if not isinstance(day, str):
            measured_at = row.get("measured_at")
            if measured_at is None:
                continue
            try:
                day = datetime.fromtimestamp(float(measured_at)).date().isoformat()
            except (TypeError, ValueError, OSError):
                continue

        entry = _normalize_entry(day, row)
        if entry:
            normalized_rows.append(entry)

    normalized_rows.sort(key=lambda item: item["date"])
    deduped: dict[str, dict[str, Any]] = {item["date"]: item for item in normalized_rows}
    return [deduped[day] for day in sorted(deduped)]


def fetch_withings_history(days: int = 90) -> list[dict[str, Any]]:
    """
    Return normalized body composition history for the last N days.

    The function never raises for missing data and always returns a list.
    """
    try:
        requested_days = int(days)
    except (TypeError, ValueError):
        requested_days = 90
    requested_days = max(1, requested_days)

    snapshot_rows = _load_history_from_snapshots(requested_days)
    if snapshot_rows:
        return snapshot_rows

    return _load_live_history(requested_days)


__all__ = ["fetch_withings_history", "OUTPUT_FIELDS"]
