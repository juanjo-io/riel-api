# Riél API — Project Context for Claude Code

## What this is
Riél is a B2B underwriting intelligence API for LATAM informal-sector merchants (Colombia, Mexico).
It generates a 0–100 credit score from 90 days of bank transaction data, produces an approve/review/decline recommendation, and suggests a credit limit in COP.

---

## Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn |
| Language | Python 3.9+ |
| Data providers | Prometeo (live), Mock (demo) |
| Payments | Stripe (disbursement via Payment Links) |
| Autonomous data | x402 challenge/response (HMAC-SHA256) |
| Frontend | Vanilla HTML/CSS/JS (demo.html, connect.html) |
| Deploy | Railway (auto-deploy on push to `main`) |
| Repo | https://github.com/juanjo-io/riel-api |

---

## Key files

```
main.py               — FastAPI app, all routes, auth, x402 helpers
features.py           — extract_features(): 6-signal feature extraction
scorer.py             — calculate_riel_score(): weighted scoring formula
providers/
  base.py             — DataProvider ABC
  registry.py         — get_provider(name) — lazy, reads env at call time
  mock_provider.py    — 3 deterministic merchant profiles
  prometeo_provider.py— Prometeo SDK wrapper (dynamic login)
  belvo_provider.py   — legacy, unused
connect.html          — 5-screen bank-linking SPA (landing→bank→creds→loading→result)
demo.html             — scoring demo UI (mock + prometeo toggle)
```

---

## Scoring formula

```
score = payment_consistency×30
      + min(counterparty_diversity/20, 1)×20
      + merchant_ratio×15
      + income_stability×20
      + (10 if repayment_proxy)
      + min(tenure_days/180, 1)×5
```

| Score | Recommendation | Limit |
|---|---|---|
| ≥ 70 | approve | COP 300 000 |
| 50–69 | review | COP 150 000 |
| < 50 | decline | 0 |

---

## Data providers

### Mock provider (`DATA_PROVIDER=mock`)
Three deterministic merchant profiles — use these link IDs:

| Link ID | Merchant | Score | Decision |
|---|---|---|---|
| `a1b2c3d4-0001-0001-0001-000000000001` | Restaurante El Patio | 77 | approve |
| `a1b2c3d4-0002-0002-0002-000000000002` | Distribuidora Velásquez | 51 | review |
| `a1b2c3d4-0003-0003-0003-000000000003` | Tienda Nueva | 22 | decline |

`GET /merchants` returns this list.

### Prometeo provider (`DATA_PROVIDER=prometeo`)
- Sandbox credentials in `.env`: `PROMETEO_API_KEY`, `PROMETEO_PROVIDER=test`, `PROMETEO_USERNAME=12345`, `PROMETEO_PASSWORD=gfdsa`
- `registry.py` imports `PrometeoProvider` lazily to avoid its async httpx SDK creating event-loop conflicts with AnyIO worker threads.
- `POST /connect/score` does a dynamic login with caller-supplied `{bank, username, password}` — does not use env-var credentials.

---

## API key authentication

Protected endpoints: `POST /score`, `POST /agent/procure`
Header: `X-API-Key: <key>`
Keys loaded from `API_KEYS` env var (format: `key:ClientName,key2:ClientName2,...`).

| Key | Client |
|---|---|
| `riel_sk_int_46a500956dbeb8ce7874ff7e` | Internal |
| `riel_sk_r2_656a3def4e6dcd0dbb2b4493` | R2 Pilot |
| `riel_sk_demo_28cf009ae77c8667587968f5` | Demo (hardcoded in demo.html) |
| `riel_sk_addi_bf0cb22c7184b4d482f82b31` | Addi |
| `riel_sk_konfio_400506020b578f7517f55175` | Konfio |
| `riel_sk_dinie_e319161f96a634741a0313a3` | Dinie |
| `riel_sk_belvo_04912460d5169c55b619f2ac` | Belvo |

`GET /me` returns the key metadata for a valid key.

---

## API routes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | — | Health ping |
| GET | `/health` | — | Status + active provider |
| GET | `/merchants` | — | List mock merchant profiles |
| POST | `/score` | X-API-Key | Score by link_id |
| POST | `/agent/procure` | X-API-Key | Autonomous x402 procure + score |
| POST | `/agent/evaluate` | — | Score + Stripe Payment Link |
| POST | `/connect/score` | — | Bank-link flow: dynamic Prometeo login |
| GET | `/connect` | — | Serve connect.html |
| GET | `/demo` | — | Serve demo.html |
| GET | `/me` | X-API-Key | Return key metadata |
| GET | `/data/transactions` | x402 Bearer | Raw transaction data (x402 gated) |
| POST | `/belvo-token` | — | Legacy Belvo token proxy |
| POST | `/create-widget-session` | — | Legacy Belvo widget session |

---

## Environment variables (`.env` — never committed)

```
DATA_PROVIDER=mock
API_KEYS=<full comma-separated key:name string>
BELVO_SECRET_ID=...
BELVO_SECRET_PASSWORD=...
BELVO_ENV=sandbox
STRIPE_SECRET_KEY=...
STRIPE_MPP_SECRET=...
PROMETEO_API_KEY=...
PROMETEO_PROVIDER=test
PROMETEO_USERNAME=12345
PROMETEO_PASSWORD=gfdsa
SELF_BASE_URL=http://localhost:8000
```

All of these must also be set in Railway's environment variable panel.

---

## Deployment

- **Platform:** Railway, connected to `github.com/juanjo-io/riel-api`
- **Trigger:** Every push to `main` auto-deploys
- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT` (in `railway.toml`)
- **Live base URL:** set in Railway dashboard

To deploy: commit changed files and `git push origin main`.

---

## Local dev

```bash
# Start server (mock mode)
python3 -m uvicorn main:app --port 8001

# Quick smoke test
curl http://localhost:8001/health

# Score all three mock merchants
for id in 0001 0002 0003; do
  curl -s -X POST http://localhost:8001/score \
    -H "Content-Type: application/json" \
    -H "X-API-Key: riel_sk_int_46a500956dbeb8ce7874ff7e" \
    -d "{\"link_id\": \"a1b2c3d4-00${id}-00${id}-00${id}-000000000${id}\"}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['riel_score'], d['recommendation'])"
done
```

---

## Workflow rules

1. **Always use Claude Code** for all code changes — do not edit files manually outside this session.
2. **Always deploy to Railway** after any change by committing and pushing to `main`.
3. `DATA_PROVIDER=mock` is the default for local dev and Railway sandbox. Switch to `prometeo` only for live bank testing.
4. Never commit `.env`. All secrets live in Railway's env var panel.
5. `registry.py` reads `DATA_PROVIDER` at call time (not import time) — do not add module-level `os.getenv` calls for this value.
6. `PrometeoProvider` must stay lazily imported inside `get_provider()` to avoid AnyIO event-loop conflicts.

---

## Current status (as of 2026-04-07)

- Mock scoring pipeline fully working: all 3 profiles return correct scores (77/51/22)
- API key auth live on `/score` and `/agent/procure`
- `/connect` — full 5-screen bank-linking SPA with Prometeo integration; bank selection is a full-page desktop layout (1160px wide, 9 CO + 9 MX banks)
- `/demo` — scoring demo with mock/prometeo toggle, all Belvo references replaced with Prometeo
- Railway deployment active and auto-deploying on push to `main`
- Prometeo sandbox available but returns sparse data (test account); mock provider used for all demos
