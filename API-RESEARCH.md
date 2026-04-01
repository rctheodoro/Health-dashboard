# Health Dashboard — API Research
*Compiled by Alfred overnight, March 23 2026*

---

## Summary

Good news: all four data sources are accessible without enterprise agreements or paying third parties. The strategy is to use the official Oura API, two community-built Python libraries for Garmin and Eight Sleep, and a periodic Apple Health XML export. This is enough to build a fully functional personal health dashboard.

---

## 1. Oura Ring — ✅ Official API, Best-in-Class

**Accessibility**: Completely open. Free personal access token.
**Documentation**: `cloud.ouraring.com/v2/docs`
**Auth method**: Personal access token (no OAuth flow needed for personal use)

### How to get your token
1. Go to `cloud.ouraring.com/personal-access-tokens`
2. Create a token — takes 2 minutes

### Available data endpoints (v2)
| Endpoint | Data |
|---|---|
| `/v2/usercollection/daily_sleep` | Sleep score, efficiency, latency, sleep stages (deep/REM/light), total sleep, restfulness |
| `/v2/usercollection/daily_readiness` | Readiness score, HRV balance, body temperature delta, recovery index, resting HR |
| `/v2/usercollection/daily_activity` | Steps, active calories, equivalent walking distance, sedentary time, activity score |
| `/v2/usercollection/heartrate` | Continuous HR data (5-min granularity) |
| `/v2/usercollection/hrv` | HRV (RMSSD) during sleep at 5-min intervals |
| `/v2/usercollection/sleep` | Per-session sleep data (multiple periods if naps) |
| `/v2/usercollection/sleep_time` | Optimal bedtime recommendation |
| `/v2/usercollection/spo2` | Blood oxygen saturation |
| `/v2/usercollection/workout` | Auto-detected workout sessions |
| `/v2/usercollection/personal_info` | Age, height, weight |

### Sample call
```bash
curl -X GET "https://api.ouraring.com/v2/usercollection/daily_sleep?start_date=2026-03-20&end_date=2026-03-23" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Rating: ⭐⭐⭐⭐⭐
Best API of the four. Consistent, well-documented, free, all data available. Start here.

---

## 2. Garmin Fenix 8 Pro — ✅ Unofficial Python Library (Actively Maintained)

**Accessibility**: Unofficial reverse-engineered API. No Garmin approval needed.
**Library**: `python-garminconnect` by cyberjunky
**GitHub**: `github.com/cyberjunky/python-garminconnect`
**Auth method**: Garmin account credentials (email + password), with session token caching

### What you get (127+ endpoints)
| Category | Key data |
|---|---|
| Daily Health | Steps, body battery, stress, heart rate, calories |
| Advanced Health Metrics | HRV status, VO2max, training readiness, training load |
| Sleep | Sleep stages, sleep score (via Garmin's algorithm) |
| Activities & Workouts | All activities incl. beach volleyball, swimming, tennis with GPS + HR zones |
| Body Composition | Weight, muscle mass, body fat (if using compatible scale) |
| Historical Data | Any date range queries |

### Key methods for this project
```python
import garminconnect

garmin = garminconnect.Garmin(email, password)
garmin.login()

# The big ones:
garmin.get_hrv_data(date)           # HRV status + 5-day trend
garmin.get_daily_steps(date)         # Steps + active minutes
garmin.get_body_battery(date)        # Body battery 0-100
garmin.get_training_readiness(date)  # Training readiness score
garmin.get_vo2max()                  # Current VO2max estimate
garmin.get_activities(0, 10)         # Last 10 activities
garmin.get_sleep_data(date)          # Sleep data from Garmin's perspective
```

### Installation
```bash
pip install garminconnect
```

### ⚠️ Risk note
This is unofficial and relies on reverse-engineered endpoints. Garmin *could* block it, though the library has been actively maintained for 5+ years and has a large user base. Store credentials securely (env vars, not plaintext). Garmin sometimes requires MFA — the library handles this with a callback.

### Rating: ⭐⭐⭐⭐
Very capable. Occasional authentication hiccups when Garmin pushes app updates. Worth it for the data richness.

---

## 3. Eight Sleep — ⚠️ Unofficial OAuth2 Library (Community-Built)

**Accessibility**: Eight Sleep has no official public API. Community reverse-engineered their OAuth2 flow.
**Libraries**:
- `pyeight` by Apollo-Sunbeam: `github.com/Apollo-Sunbeam/pyeight` (newer OAuth2)
- `eight_sleep` by lukas-clarke: `github.com/lukas-clarke/eight_sleep` (Home Assistant, OAuth2)
**Auth**: OAuth2 using Eight Sleep account credentials (auth-api.8slp.net)

### Available data
| Data | Notes |
|---|---|
| Sleep stages | Light/deep/REM/awake time |
| Sleep score | Eight Sleep's proprietary score |
| HRV during sleep | Heart rate variability |
| Respiratory rate | Breaths per minute |
| Heart rate | Average and detailed |
| Bed temperature | Left/right side |
| Sleep latency | Time to fall asleep |
| Presence detection | Whether someone is in bed |

### ⚠️ Caveats
- This is the trickiest of the four. Eight Sleep actively changes their app/API and community libraries break periodically.
- Most reliable approach: use the Home Assistant integration as a reference for current auth flows
- An alternative is to use **Terra API** (tryterra.co) which officially supports Eight Sleep, but it costs $499/month minimum — overkill for personal use.
- **Recommendation**: Implement Eight Sleep last. Use Oura + Garmin first, then add Eight Sleep if the pyeight library works.

### Rating: ⭐⭐⭐
Data is excellent. Library stability is the variable.

---

## 4. Apple Health — ✅ XML Export + Python Parser

**Accessibility**: No external API. Apple Health data lives on-device. Two access paths:

### Option A: Periodic XML export (recommended for v1)
1. On iPhone: Health app → Profile icon → Export All Health Data → produces `export.zip`
2. Parse `export.xml` with Python:
```bash
pip install apple-health-parser  # or apple-health-exporter
```
3. Automate: create a Shortcut on iPhone that runs weekly and AirDrops/shares the export
4. Parse the XML and load into the dashboard

**Apple Health data types in export:**
- Heart rate (all sources), steps, active energy, resting energy
- Sleep analysis (from all connected apps/devices)
- VO2max (Apple Watch estimate if applicable)
- Blood oxygen, ECG data
- Workout sessions (auto-imported from Garmin, Oura, etc.)
- Weight, height, BMI

### Option B: Native iOS app with HealthKit (for future phases)
- Build a small iOS app in Swift that reads HealthKit and sends data to a local server
- More complex but enables real-time sync
- Good for Phase 2 when building the actual iOS dashboard app

### Rating: ⭐⭐⭐
Data is comprehensive (aggregates everything), but manual export is clunky. Good for weekly batch processing in v1.

---

## Recommended Build Sequence

### Phase 1: Daily Report (Start Here — 1-2 days of work)
Build a Python script that runs nightly and generates a health report:

```
1. Pull Oura API (personal token) → sleep, readiness, HRV
2. Pull Garmin API (python-garminconnect) → body battery, VO2max, training load, activities
3. Combine into a daily health briefing
4. Deliver via Alfred/Telegram every morning
```

This alone covers ~80% of the value with the least complexity.

### Phase 2: Eight Sleep integration
- Add pyeight to the nightly pull
- Cross-reference sleep data: Oura vs Eight Sleep vs Garmin (the "which device is right?" comparison Renato wants)

### Phase 3: Apple Health batch analysis
- Weekly Apple Health export → parse → long-term trend analysis
- Good for monthly reviews

### Phase 4: Web/iOS dashboard
- Once data pipeline is proven, build the actual visual dashboard
- Could be a web app first (HTML + charts), then native iOS

---

## Implementation Notes

### Architecture for Phase 1
```
cron (nightly 05:00) 
  → Python script (sub-agent)
    → Oura API call
    → Garmin API call  
    → Aggregate + score
    → Format report
  → Alfred delivers to Telegram
```

### Data Storage
- Simple: JSON files per day (`health-data/2026-03-23.json`)
- Better: SQLite database for queries and trend analysis
- Best: Postgres if building a proper web app later

### Credentials Management
```bash
# Environment variables (not plaintext in code):
OURA_ACCESS_TOKEN=...
GARMIN_EMAIL=...
GARMIN_PASSWORD=...
EIGHT_SLEEP_EMAIL=...
EIGHT_SLEEP_PASSWORD=...
```

Store in `.env` file in workspace (never committed to git if repo is public).

### Key Metrics to Track (Renato's priorities)
| Metric | Source | Relevance |
|---|---|---|
| HRV (RMSSD) | Oura primary, Garmin secondary | Recovery quality |
| Readiness score | Oura | Daily decision: train hard or recover |
| Body battery | Garmin | Real-time energy status |
| Sleep score | Oura + Eight Sleep comparison | Cross-validate |
| VO2max trend | Garmin | Longevity metric (Attia) |
| Training load | Garmin | Avoid overtraining, track beach volleyball frequency |
| Deep sleep % | Oura + Eight Sleep | Quality sleep indicator |
| Resting HR | Oura | Baseline health trend |

---

## Next Steps for Renato

1. **Generate your Oura personal access token** → `cloud.ouraring.com/personal-access-tokens` (2 min)
2. **Confirm Garmin account credentials** are known (needed for python-garminconnect)
3. **Tell Alfred** to build the Phase 1 daily health report script (sub-agent job)
4. Decide: deliver health report as part of the morning briefing, or as a separate daily message?

---

*Research complete. No API keys required to proceed beyond Oura token generation.*
*All libraries are pip-installable. Eight Sleep is the only uncertain element.*
