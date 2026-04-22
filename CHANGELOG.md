# Changelog

## 2026-04-05

### Investigated — Garmin Integration Stall

Investigated the repo and runtime assumptions to reconstruct why Garmin never started returning data:

- Dashboard UI and JSON schema already expected Garmin fields (`body_battery`, `training_readiness`, `activities`, `sleep`, `hrv`)
- Saved data files still had `garmin: null`, meaning Garmin never completed one successful fetch in this workspace state
- Root cause: `scripts/daily_health_report.py` only attempted a fresh `GARMIN_EMAIL` / `GARMIN_PASSWORD` login on every run, even though `API-RESEARCH.md` already documented that MFA-era Garmin auth should use a cached `garth` token store
- Local investigation found no `~/.garth` token cache present, so the documented workaround had not actually been executed on this machine

### Changed — Garmin Auth Fallback

Updated `scripts/daily_health_report.py` to:

- prefer `GARMIN_TOKEN_STORE` / `~/.garth` when available
- fall back to email/password login only if token login is unavailable
- emit clearer warnings when Garmin is unconfigured or the token cache is missing

Updated `scripts/.env.example`, `scripts/README.md`, and `PROJECT.md` so the next operator can see the missing Garmin step immediately.

### Added — New Oura Ring API Endpoints

Added 5 new Oura v2 endpoints to `fetch_oura()` in `scripts/daily_health_report.py`:

- **VO2max** (`/v2/usercollection/vo2_max`) — stored as `result["vo2_max"]`
- **Cardiovascular Age** (`/v2/usercollection/daily_cardiovascular_age`) — stored as `result["cardiovascular_age"]`
- **Daily Resilience** (`/v2/usercollection/daily_resilience`) — stored as `result["resilience"]`
- **Daily Stress** (`/v2/usercollection/daily_stress`) — stored as `result["stress"]`
- **SpO2** (`/v2/usercollection/daily_spo2`) — stored as `result["spo2"]`

Added new `🫀 VITALS (Oura)` section to `print_report()` (displayed after Readiness, before Energy) showing:
- VO2max in mL/kg/min
- Cardiovascular Age in years
- Resilience level (capitalized)
- Stress summary with high-stress minutes
- Average SpO2 percentage

All new endpoints handle missing/empty data gracefully (Oura Membership required; degrades to "N/A" without crashing).
