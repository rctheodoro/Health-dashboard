#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
DASHBOARD_INDEX = PROJECT_DIR / "dashboard" / "index.html"
STATIC_DIR = PROJECT_DIR / "static"
STATIC_INDEX = STATIC_DIR / "index.html"
STATIC_DATA = STATIC_DIR / "data.json"
SKIP_FILES = {"strava_tokens.json", "morpheus_manual.json"}


FETCH_ALL_REPLACEMENT = """    async function fetchAll() {
      setStatus('Loading dashboard…', PALETTE.yellow);
      const sleepComparisonEl = $('sleep-comparison-panel');
      const sleepHistoryEl = $('sleep-history');
      const activityTableEl = $('activity-table');

      sleepComparisonEl.innerHTML = loadingMarkup('Fetching device sleep summaries…');
      sleepHistoryEl.innerHTML = loadingMarkup('Building 30-day sleep history…');
      activityTableEl.innerHTML = loadingMarkup('Loading Garmin activities…');

      try {
        const payload = await fetchJson('data.json');

        state.historyData = Array.isArray(payload.history) ? payload.history : [];
        state.todayData = payload.today_data || null;
        state.garminTrends = Array.isArray(payload.garmin_trends) ? payload.garmin_trends : [];
        state.garminActivities = Array.isArray(payload.garmin_activities) ? payload.garmin_activities : [];
        state.withingsHistory = Array.isArray(payload.withings_history) ? payload.withings_history : [];
        state.eightSleepHistory = Array.isArray(payload.eightsleep_history) ? payload.eightsleep_history : [];
        state.longterm = payload.garmin_longterm || { rows: [], message: null };
        state.fetchedAt = new Date();
        state.longtermFetchedAt = new Date();

        if (!state.todayData) {
          throw new Error('Static dashboard data is unavailable');
        }

        renderDashboard();
        setUpdated('core', state.fetchedAt);
        setUpdated('longterm', state.longtermFetchedAt);
        setStatus('Static dashboard loaded', PALETTE.green);
      } catch (error) {
        setStatus(`Load failed: ${error.message}`, PALETTE.red);
        $('sleep-comparison-panel').innerHTML = emptyMarkup(error.message);
        $('sleep-history').innerHTML = emptyMarkup('Unable to build sleep history right now.');
        $('activity-table').innerHTML = emptyMarkup('Unable to load Garmin activities right now.');
      }
    }
"""


def load_saved_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(DATA_DIR.glob("*.json")):
        if path.name in SKIP_FILES:
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("date"), str):
            records.append(payload)
    records.sort(key=lambda record: record["date"])
    return records


def coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_withings_history(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        payload = record.get("withings")
        if not isinstance(payload, dict):
            continue

        row = {
            "date": record["date"],
            "weight_kg": coerce_float(payload.get("weight_kg")),
            "fat_ratio_pct": coerce_float(payload.get("fat_ratio_pct")),
            "fat_mass_kg": coerce_float(payload.get("fat_mass_kg")),
            "muscle_mass_kg": coerce_float(payload.get("muscle_mass_kg")),
        }
        if all(row[key] is None for key in ("weight_kg", "fat_ratio_pct", "fat_mass_kg", "muscle_mass_kg")):
            continue
        rows.append(row)
    return rows


def build_eightsleep_history(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        row = {"date": record["date"]}
        payload = record.get("eightsleep")
        if isinstance(payload, dict):
            row.update(payload)
        rows.append(row)
    return rows


def build_static_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    today_data = records[-1] if records else None
    return {
        "today_data": today_data,
        "history": records,
        "garmin_trends": [],
        "garmin_activities": [],
        "garmin_today": None,
        "withings_history": build_withings_history(records),
        "eightsleep_history": build_eightsleep_history(records),
        "garmin_longterm": {
            "rows": [],
            "message": "Garmin not configured",
        },
        "ollama_status": {
            "available": False,
        },
    }


def rewrite_index() -> None:
    html = DASHBOARD_INDEX.read_text()
    pattern = re.compile(
        r"    async function fetchAll\(\) \{.*?^    \}\n(?=\n    function renderDashboard\(\))",
        re.DOTALL | re.MULTILINE,
    )
    updated_html, replacements = pattern.subn(FETCH_ALL_REPLACEMENT.rstrip(), html, count=1)
    if replacements != 1:
        raise RuntimeError("Could not replace fetchAll() in dashboard/index.html")
    STATIC_INDEX.write_text(updated_html)


def main() -> None:
    records = load_saved_records()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    payload = build_static_payload(records)
    STATIC_DATA.write_text(json.dumps(payload, indent=2) + "\n")

    shutil.copy2(DASHBOARD_INDEX, STATIC_INDEX)
    rewrite_index()

    print(f"Wrote {STATIC_DATA.relative_to(PROJECT_DIR)}")
    print(f"Wrote {STATIC_INDEX.relative_to(PROJECT_DIR)}")
    print(f"Loaded {len(records)} dated records")


if __name__ == "__main__":
    main()
