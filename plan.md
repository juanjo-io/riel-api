# Riél Refactor Plan — Argentina SMB Risk Monitoring

## Discovery Summary

### Framework & Runtime
- **Framework:** FastAPI + Uvicorn (Python 3.9+)
- **Run:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Dev:** `DATA_PROVIDER=mock python3 -m uvicorn main:app --port 8000 --reload`
- **Test:** `python3 test_scoring.py` (unit), `python3 test_live.py` (integration)
- **Deploy:** git push to `main` → Railway auto-deploys

### Auth Flow
- **Lender auth:** magic-link via `itsdangerous.URLSafeTimedSerializer`
  - `POST /lender/login-request` → signed token, 15 min TTL
  - `GET /lender/magic-login?token=...` → sets `lender_session` cookie (HttpOnly, 1 day)
  - `POST /lender/logout` → clears cookie
  - `get_current_lender()` Depends → guards `/dashboard` and `/dashboard/stats`
  - Allowed emails: `LENDER_EMAILS` env var (comma-separated)
- **API key auth:** `verify_api_key()` Depends → checks Supabase `api_keys` table first, then `VALID_API_KEYS` env fallback
  - Guards: `POST /score`, `POST /agent/procure`, `GET /score/{id}/explain`, `GET /dashboard/stats`

### Current Scoring Pipeline
- `features.py` → `extract_features(txs)` → 6 signals: payment_consistency, counterparty_diversity, merchant_ratio, income_stability, repayment_proxy, tenure_days
- `scorer.py` → `calculate_riel_score(features)` → weighted sum → 0–100 → approve/review/decline + COP limit
- Currency: COP only. No FX awareness. No time-window deterioration.

### Current /connect Page
- `connect.html` — 5-screen SPA: landing → bank grid → credentials → loading → result
- Bank grid: 9 CO + 9 MX banks, country tabs, coming-soon tiles, dev provider
- `POST /connect/score` — reads `DATA_PROVIDER` env, mock or Prometeo branch
- Returns: `riel_score`, `recommendation`, `suggested_limit_cop`, `confidence`, `features`

### Current Dashboard
- `dashboard.html` — Chart.js 4, warm off-white design system
- KPI strip: merchants scored, approval rate, under review, declined
- Charts: score distribution, approval rate over time (weekly), avg credit limit by bank
- Fetches from `GET /dashboard/stats` (auth-gated)
- `dashboard_stats()` reads Supabase `score_history` or in-memory fallback

### Data Layer
- `MockProvider`: 3 profiles (El Patio 77, Velásquez 51, Tienda Nueva 22) — COP, Colombia
- `PrometeoProvider`: REST wrapper around `banking.sandbox.prometeoapi.com` — httpx, session key as `?key=` param
- Supabase: `score_history`, `webhooks`, `api_keys` tables; `supa = None` fallback when env unset
- `_SEED_DATA`: 18 merchants seeded at startup (in-memory or Supabase)
- x402: `_make_challenge_id` / `_verify_challenge_id` HMAC-SHA256 infrastructure

### Env Vars
```
DATA_PROVIDER         mock | prometeo
API_KEYS              key:name,... (lender API keys)
AUTH_SECRET_KEY       itsdangerous secret
LENDER_EMAILS         comma-separated allowed emails
SUPABASE_URL / KEY    Supabase project
STRIPE_SECRET_KEY     Stripe disbursement
STRIPE_MPP_SECRET     x402 HMAC secret
PROMETEO_API_KEY      Prometeo sandbox
PROMETEO_PROVIDER     test
PROMETEO_USERNAME     12345
PROMETEO_PASSWORD     gfdsa
SELF_BASE_URL         https://web-production-f3a75.up.railway.app
```

---

## What to Reuse vs Replace

| Component | Decision | Reason |
|-----------|----------|--------|
| FastAPI app structure | **Keep** | Solid, no changes needed |
| `get_current_lender` + magic-link auth | **Keep** | Working, deployed |
| `verify_api_key` | **Keep** | Supabase-backed, working |
| `DataProvider` ABC + registry | **Keep** | Clean abstraction |
| `PrometeoProvider` | **Keep** | REST-based, tested |
| `MockProvider` (3 profiles) | **Extend** | Add Argentina mock data |
| `features.py` | **Replace** | COP/Colombia-specific; replace with Argentina 5-metric extractor |
| `scorer.py` | **Replace** | approve/review/decline → 5 actions |
| `dashboard.html` | **Replace UI** | Redesign for portfolio monitoring table |
| `connect.html` | **Keep skeleton, update result** | Bank-linking UX is fine; result screen needs new metrics |
| `_SEED_DATA` | **Replace** | Argentina merchants, ARS amounts |
| `dashboard_stats()` endpoint | **Replace** | New metrics, new response shape |
| `/score` endpoint | **Keep** | Used by API clients; can add Argentina variant |
| x402 infrastructure | **Keep** | Future `/merchant/{id}/refresh` |
| Belvo references | **Remove eventually** | Unused legacy |
| Stripe disbursement | **Defer** | Out of scope for monitoring product |

---

## Phased Implementation Plan

### Phase 0 — Foundation (no breaking changes)
**Goal:** Argentina feature extractor and scorer alongside existing ones. Nothing changes in prod.

1. Create `argentina_features.py` — extract 5 metrics from transactions (ARS-aware)
2. Create `argentina_scorer.py` — compute action from 5 metrics
3. Add 3 Argentina mock merchant profiles to `mock_provider.py`
4. Add `GET /argentina/score/{link_id}` endpoint (API-key gated) — runs new pipeline
5. **Verify:** existing `/score` still works for all 3 mock profiles

### Phase 1 — Portfolio Monitoring Backend
**Goal:** API endpoints that power the new dashboard.

1. Add Supabase `merchants` table (SQL in docs)
2. Add `GET /portfolio` — returns all merchants with current metrics
3. Add `GET /merchant/{id}` — single merchant full metrics + trend data
4. Update `_SEED_DATA` with Argentina merchants (ARS, Argentine banks)
5. **Verify:** `GET /portfolio` returns 5 required metrics per merchant

### Phase 2 — Dashboard UI Replacement
**Goal:** Replace `dashboard.html` with portfolio monitoring page.

1. Replace KPI strip with action distribution (Healthy/Monitor/Review Now/Reduce/Opportunity)
2. Replace charts with merchant table (sortable, filterable by action)
3. Add trend sparklines per metric
4. **Verify:** `/dashboard` loads, table renders, auth still required

### Phase 3 — Merchant Detail Page
**Goal:** `/merchant/{id}` page.

1. Create `merchant.html` — full metric breakdown + trend charts
2. Add `GET /merchant/{id}` route serving HTML (auth-gated)
3. Wire to `GET /merchant/{id}/data` JSON endpoint
4. **Verify:** click through from portfolio → detail page

### Phase 4 — Connect Flow Update
**Goal:** `/connect` produces Argentina risk output.

1. Update result screen to show 5 metrics + action (not riel_score/COP limit)
2. Update `POST /connect/score` to run Argentina pipeline
3. **Verify:** mock connect flow produces Survival Runway etc.

### Phase 5 — x402 Refresh (Future)
**Goal:** Per-merchant on-demand re-underwriting, paid.

1. `POST /merchant/{id}/refresh` with x402 challenge/response
2. Triggers fresh Prometeo pull + Argentina scorer
3. Returns metric delta

---

## Verification Steps Per Phase
Each phase must pass before the next begins:
- `curl /health` → 200
- Existing mock scoring (`/score` with 3 profiles) → unchanged scores
- New endpoints respond with correct shape
- `/dashboard` still requires `lender_session` cookie
- Railway deploy succeeds (check logs)
