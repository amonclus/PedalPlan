# Training Analysis Dashboard

## Project Overview

A Streamlit web application that connects to the Strava API to fetch cycling activity data and uses a Claude AI agent to generate personalized weekly training plans. Designed for amateur cyclists who want smart training guidance without the cost of platforms like TrainingPeaks.

## Goals

- Connect to Strava via OAuth and pull recent activity history
- Display a clean dashboard with key training metrics
- Allow the user to configure training parameters (FTP, HR zones, target hours)
- Generate a week-by-week training plan every Sunday using Claude, informed by actual recent training load

## Tech Stack

- **Python** — all backend logic, API calls, data processing
- **Streamlit** — dashboard UI
- **Strava API** — activity data source (OAuth 2.0)
- **Anthropic Python SDK** — Claude agent for training plan generation

## Key Features

### Strava Integration
- OAuth 2.0 authentication flow (authorization code + token refresh)
- Fetch recent activities (rides): distance, duration, elevation, average power, average HR, TSS if available
- Store tokens locally (e.g. `tokens.json`) and auto-refresh when expired
- Pull enough history to compute training load (at least 6 weeks)

### Training Metrics (computed locally)
- **CTL** (Chronic Training Load) — 42-day exponentially weighted average of daily TSS
- **ATL** (Acute Training Load) — 7-day exponentially weighted average of daily TSS
- **TSB** (Training Stress Balance) — CTL minus ATL (form)
- **TSS estimation** — if power data is unavailable, estimate from HR and duration using the hrTSS formula

### User Configuration (sidebar inputs)
- FTP (watts)
- Heart rate zones (Zone 1–5 boundaries in bpm)
- Desired weekly training hours
- Goal/focus (e.g. base fitness, race prep, recovery)

### Claude Training Plan Agent
- Receives: recent activity summary, computed CTL/ATL/TSB, user config
- Outputs: a structured 7-day plan for the upcoming week
- Each day specifies: workout type, duration, intensity zone, and brief description
- Plan should respect training load (avoid spikes) and factor in current fatigue (TSB)
- Triggered manually by the user (e.g. a "Generate Plan" button), intended for weekly use on Sundays

### Dashboard Views
1. **Overview** — CTL, ATL, TSB trend chart; recent activity list
2. **Plan** — Current week's generated training plan, displayed day by day
3. **Settings** — FTP, HR zones, weekly hours target

## Project Structure

```
Training_analysis/
├── CLAUDE.md
├── .env                    # STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, ANTHROPIC_API_KEY
├── requirements.txt
├── app.py                  # Streamlit entry point
├── auth/
│   └── strava_oauth.py     # OAuth flow and token management
├── data/
│   └── strava_client.py    # Strava API calls and activity parsing
├── metrics/
│   └── training_load.py    # CTL, ATL, TSB, TSS calculations
├── agent/
│   └── planner.py          # Claude agent prompt construction and call
└── tokens.json             # Persisted OAuth tokens (gitignored)
```

## Environment Variables

```
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_REDIRECT_URI=http://localhost:8501   # Streamlit default port
ANTHROPIC_API_KEY=
```

## Strava API Notes

- Base URL: `https://www.strava.com/api/v3`
- Auth URL: `https://www.strava.com/oauth/authorize`
- Token URL: `https://www.strava.com/oauth/token`
- Scopes needed: `activity:read_all`
- Token expiry: access tokens last 6 hours; always check `expires_at` and refresh proactively
- Rate limits: 100 requests/15 min, 1000/day — cache activity data locally to avoid hitting limits

## Claude Agent Notes

- Use `claude-sonnet-4-6` model (current production model)
- Include prompt caching on the system prompt (activity history is large and repeated)
- System prompt should establish the agent as a cycling coach with knowledge of polarized/pyramidal training models
- User message should contain: formatted activity log, current CTL/ATL/TSB, and user parameters
- Response should be structured (ask Claude to respond in a consistent format, e.g. JSON or markdown table per day)

## Development Notes

- Run locally with: `streamlit run app.py`
- The Strava OAuth redirect must match the URI registered in the Strava API application settings
- For local dev, the OAuth flow can be handled inline in Streamlit using `st.query_params` to capture the auth code
- `tokens.json` must be in `.gitignore`
- Use `python-dotenv` to load `.env` in development

## Out of Scope (for now)

- Multi-user support
- Race calendar integration
- Zwift or other platform connections
- Mobile layout optimization
- Automated weekly plan generation (user triggers it manually)
