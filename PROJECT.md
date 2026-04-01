# Health Dashboard — Consolidating All Health Data

## Vision
A single app/dashboard that pulls data from ALL of Renato's health devices and presents a unified view. No existing app does this well.

## Data Sources
- **Eight Sleep**: sleep stages, bed temperature, HRV during sleep, respiratory rate
- **Oura Ring**: sleep scores, readiness, activity, HRV, temperature trends, SpO2
- **Garmin Fenix 8 Pro**: VO2max estimate, training load, body battery, steps, HR zones, GPS activities, beach volleyball sessions
- **Apple Health**: aggregated data from all devices
- **Manual inputs**: weight, body composition, sauna sessions, subjective energy/mood

## Key Features (brainstorm)
1. **Daily Score**: one number combining sleep + readiness + training load
2. **Sleep Consolidation**: merge Eight Sleep + Oura + Garmin sleep data into one view
3. **Training Load**: beach volleyball frequency, gym sessions, zone 2 cardio tracking (Attia protocol)
4. **Recovery Metrics**: HRV trends, readiness vs training load balance
5. **Longevity Tracking**: VO2max trend, strength benchmarks, key biomarkers
6. **Sauna Log**: track sauna sessions (Huberman protocol: 80-100°C, 20-30min)
7. **Trend Analysis**: weekly/monthly/quarterly trends with AI-generated insights
8. **Actionable Alerts**: "your HRV dropped 15% this week, consider a recovery day"

## Technical Approach (TBD)
- APIs: Eight Sleep API, Oura API (well documented), Garmin Connect (unofficial), Apple HealthKit
- Could be: iOS app (Swift), web app, or even a daily automated report
- Start with data collection + daily report, evolve into full app

## Status
- Phase: **Phase 1 Script Complete** (code ready, awaiting credentials)
- Research: `API-RESEARCH.md` — all four APIs documented with code examples
- Script: `scripts/daily_health_report.py` — fully built, pulls Oura + Garmin, computes weighted score, prints formatted report, saves JSON to `data/`
- **Oura integration**: ✅ DONE — token configured, Daily Health Report cron running since March 2026
- **Eight Sleep integration**: ✅ DONE — pulling sleep stages, HRV, respiratory rate
- **Garmin integration**: TBD — needs credentials or unofficial API approach
- Next: Decide whether to evolve into a unified dashboard (combining all sources) or keep as separate daily report

## Renato's Ideas

### Sleep Comparison View
- Show sleep data from ALL sources (Eight Sleep, Oura, Garmin) side by side
- Calculate daily **average, high, and low** across all devices for each metric
- Repeat for: sleep score, HRV, deep sleep %, REM %, sleep latency, respiratory rate
- Goal: see where devices agree and where they diverge
- "Which device is the most accurate for ME?" over time

### Training Schedule
- **Main workouts**: beach volleyball (3x/week goal), strength training (home gym), swimming, tennis
- Calendar view with planned vs completed
- Integration with Garmin activities for auto-logging
- Track Attia's 4 pillars: strength, zone 2, VO2max, stability

### Office Micro-Exercises / Physio
- Library of quick exercises doable at a desk/office
- Scheduled reminders throughout the workday
- Focus on: posture correction, hip mobility (desk sitting), shoulder/neck tension, wrist/forearm (from typing)
- Physio-style routines for injury prevention
- Timer-based: "5 min every 2 hours" type prompts

### Unified Daily Score
- One number combining sleep quality + readiness + training load balance
- AI-generated insight: "your HRV dropped 15%, consider recovery day"
