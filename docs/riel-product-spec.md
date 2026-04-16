# Riél — Product Spec v2 (Argentina SMB)

## Purpose
Early-warning and re-underwriting tool for lenders with existing SMB portfolios in Argentina.
Not a generic dashboard. The core question is: **"Should I act on this merchant today?"**

---

## Target Market
- Argentina-first
- SMB lenders, embedded finance players, factoring companies
- Merchants: small businesses with a bank account (tiendas, ferreterías, almacenes, kioscos, etc.)

---

## Core Risk Metrics (replace existing 6-signal scorer)

| # | Metric | Description |
|---|--------|-------------|
| 1 | **Survival Runway** | How many days of outflows can current cash cover at current burn rate |
| 2 | **Real Cash Coverage** | Inflows vs contractual obligations ratio (adjusted for FX) |
| 3 | **FX Mismatch Exposure** | Proportion of costs in USD/EUR vs revenue in ARS |
| 4 | **Revenue Concentration** | Top-3 counterparty share of total inflows (HHI proxy) |
| 5 | **Deterioration Index** | Rate of change across all 4 metrics over rolling 30/60/90d windows |

---

## Required Actions (replace approve/review/decline)

| Action | Trigger |
|--------|---------|
| **Healthy** | All metrics green, no trend degradation |
| **Monitor** | One metric amber, trend stable |
| **Review Now** | One metric red, or two amber |
| **Reduce Exposure** | Multiple red metrics or rapid deterioration |
| **Opportunity** | Metrics improving, headroom for limit increase |

---

## Required Pages

### 1. Portfolio Monitoring Page (`/dashboard`)
- Table/grid of all merchants in portfolio
- Per-merchant row: name, bank, Survival Runway, Real Cash Coverage, FX Mismatch, Revenue Concentration, Deterioration Index, Action badge
- Filter by action type
- Sortable columns
- Auth-gated (existing `get_current_lender` dependency)

### 2. Merchant Detail Page (`/merchant/{id}`)
- Full metric breakdown for one merchant
- Trend charts: 30/60/90d windows for each metric
- Transaction history summary
- Action recommendation with justification
- Future: x402-powered "Refresh Risk" button that re-underwrites on demand

### 3. Connect / Merchant Intake (`/connect`)
- Existing bank-linking SPA (keep)
- On completion: runs Argentina risk metrics instead of COP scorer
- Stores result in Supabase `score_history`

---

## Data Layer

### Current (keep)
- `DataProvider` ABC with `get_transactions(link_id)` and `get_account_summary(link_id)`
- `MockProvider` — 3 deterministic profiles; extend with Argentina mock data
- `PrometeoProvider` — REST API wrapper (sandbox working)
- Supabase: `score_history`, `webhooks`, `api_keys` tables
- Magic-link lender auth: `get_current_lender` cookie dependency

### New required
- `argentina_features.py` — extract 5 Argentina-specific metrics from transactions
- `argentina_scorer.py` — compute action recommendation from metrics
- Supabase `merchants` table: link_id, name, bank, portfolio metadata
- ARS as primary currency (not COP); FX rates for USD/EUR

---

## x402 Future Feature
`POST /merchant/{id}/refresh` — x402-gated endpoint that:
1. Triggers fresh data pull from Prometeo
2. Re-computes all 5 metrics
3. Returns updated action + metric delta
4. Charges lender per-refresh via Stripe MPP

Infrastructure already present: `_make_challenge_id`, `_verify_challenge_id`, `/data/transactions`.

---

## Out of Scope (this phase)
- Multi-lender tenant isolation (single lender for now)
- Email delivery of magic links (console print is fine for now)
- Belvo integration (legacy, unused)
- Stripe disbursement flow (unrelated to monitoring product)
