# Riel — Credit Scoring API for Latin American SMBs

Riel is a credit scoring API that pulls 90 days of open banking transaction data for small and medium businesses in Latin America, runs a scoring model, and returns a structured credit decision for lenders.

## Live Demo

- **Demo:** `https://web-production-f3a75.up.railway.app/demo`
- **Merchant Onboarding:** `https://web-production-f3a75.up.railway.app/connect`
- **Health Check:** `https://web-production-f3a75.up.railway.app/health`

***

## What It Does

A lender or fintech sends a `link_id` to `/score`. Riel fetches 90 days of bank transactions via the Prometeo open banking API, computes 6 financial signal features, and returns:

- A **Riel score** (0–100)
- A **recommendation** (`approve` / `review` / `decline`)
- A **suggested credit limit** in COP
- **6 signal features** (e.g. revenue stability, expense ratio, cash flow volatility)

***

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) |
| Deployment | Railway |
| Open Banking | Prometeo API |
| Autonomous Payments | x402 protocol |
| Database | Supabase (PostgreSQL) |
| Frontend | Vanilla HTML/CSS/JS |

***

## Architecture

```
Lender / Agent
     │
     ▼
POST /score  ──────►  PrometeoProvider.fetch_transactions(link_id)
                               │
                               ▼
                       ScoringEngine.compute(transactions)
                               │
                        ┌──────┴──────┐
                        │  6 features  │
                        └──────┬──────┘
                               ▼
                        Riel Score (0–100)
                        Recommendation
                        Credit Limit (COP)
                               │
                               ▼
                        Supabase  ◄──  persisted with timestamp
```

### Autonomous Agent Flow (`/agent/procure`)

Uses the **x402 payment protocol** for autonomous API access:

```
Agent  →  challenge  →  pay  →  fetch  →  score  →  return
```

***

## API Reference

### `POST /score`

```json
{
  "link_id": "merchant-link-id"
}
```

**Response:**
```json
{
  "score": 77,
  "recommendation": "approve",
  "credit_limit_cop": 15000000,
  "features": {
    "revenue_stability": 0.82,
    "expense_ratio": 0.61,
    "cash_flow_volatility": 0.18,
    "avg_monthly_revenue": 4200000,
    "days_negative_balance": 3,
    "recurring_revenue_pct": 0.74
  }
}
```

### `POST /agent/procure`

Autonomous scoring via x402 payment protocol. Handles challenge, payment, and score retrieval in a single pipeline.

### `GET /health`

Returns current server status and active provider.

***

## Providers

Riel uses a provider abstraction so the data source can be swapped without touching the scoring logic.

| Provider | Description |
|---|---|
| `MockProvider` | 3 pre-built Colombian merchant profiles for testing |
| `PrometeoProvider` | Live open banking — real bank transaction data |

### Mock Merchants

| Merchant | Score | Recommendation |
|---|---|---|
| Restaurante El Patio | 77 | ✅ Approve |
| Distribuidora Velásquez | 51 | 🔶 Review |
| Tienda Nueva | 22 | ❌ Decline |

***

## Frontend

### `/demo` — Lender Demo
Two-panel interface for lenders:
- **Standard Score panel** — select a mock merchant, get score + features instantly
- **Autonomous Agent panel** — enter a COP amount, watch the x402 pipeline run step-by-step

Supports toggling between MockProvider and live Prometeo.

### `/connect` — Merchant Onboarding SPA
5-screen flow embedded by lenders in their product:

1. **Landing** — permissions list, security note, CTA
2. **Bank selection** — Colombia / México tabs, bank grid
3. **Credentials** — username/password for selected bank
4. **Loading** — animated x402 pipeline progress
5. **Result** — score card with recommendation and credit limit

***

## Database

Supabase (PostgreSQL) stores every score call:

```sql
CREATE TABLE scores (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id text NOT NULL,
  score       integer NOT NULL,
  recommendation text NOT NULL,
  credit_limit_cop bigint,
  features    jsonb,
  provider    text,
  created_at  timestamptz DEFAULT now()
);
```

***

## Local Development

### Prerequisites
- Python 3.11+
- A `.env` file (see `.env.example`)

### Setup

```bash
git clone https://github.com/your-username/riel-api.git
cd riel-api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

**Never commit `.env` to version control.** All secrets are loaded via environment variables at runtime.

### Run

```bash
uvicorn main:app --reload --port 8001
```

Visit `http://localhost:8001/demo`

***

## Environment Variables Reference

| Variable | Description |
|---|---|
| `PROMETEO_API_KEY` | Prometeo open banking API key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/service key |
| `RIEL_ENV` | `development` or `production` |

See `.env.example` for the full list.

***

## Project Structure

```
riel-api/
├── main.py              # FastAPI app, route definitions
├── scoring.py           # Scoring engine and feature computation
├── providers/
│   ├── base.py          # Provider abstract class
│   ├── mock.py          # MockProvider with test merchants
│   └── prometeo.py      # PrometeoProvider (live open banking)
├── templates/
│   ├── demo.html        # Lender demo UI
│   └── connect.html     # Merchant onboarding SPA
├── .env.example         # Environment variable template
├── requirements.txt
└── README.md
```

***

## Deployment

Riel is deployed on **Railway** with environment variables set in the Railway dashboard. Push to `main` triggers automatic redeploy.

```bash
git push origin main  # triggers Railway deployment
```

***

## .env.example

```
PROMETEO_API_KEY=your_prometeo_api_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_key_here
RIEL_ENV=development
```

***

## Status

Currently in **closed beta** — testing with fintech lenders in Colombia.
