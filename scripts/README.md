# Daily Health Report

Pulls data from Oura Ring and Garmin Connect, computes a weighted overall score, prints a console report, and saves raw + computed data as JSON.

## Setup

1. **Oura token**: Go to [cloud.ouraring.com/personal-access-tokens](https://cloud.ouraring.com/personal-access-tokens) and create a Personal Access Token.

2. **Create your `.env` file**:
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` and fill in your credentials:
   - `OURA_ACCESS_TOKEN` — the token from step 1
   - `GARMIN_EMAIL` / `GARMIN_PASSWORD` — your Garmin Connect login (optional)

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

```bash
# Today's report
python daily_health_report.py

# Specific date
python daily_health_report.py 2026-03-24
```

The script will:
- Fetch data from whichever services have credentials configured
- Print a formatted report to the console
- Save a JSON file with raw and computed data

## Cron Setup

To run automatically every morning at 7:00 AM:

```bash
crontab -e
```

Add:
```
0 7 * * * cd /Users/rtbot/.openclaw/workspace/projects/health-dashboard/scripts && /usr/bin/python3 daily_health_report.py >> /tmp/health-report.log 2>&1
```

## Data Storage

Each run saves a JSON file to:

```
../data/YYYY-MM-DD.json
```

Structure:
```json
{
  "date": "2026-03-25",
  "oura": { ... },
  "garmin": { ... },
  "computed": {
    "overall_score": 80,
    "advice": "Solid. Full training OK."
  }
}
```
