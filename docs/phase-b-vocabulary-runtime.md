# Phase B vocabulary runtime contract

The authoritative HTTP contract is
[`docs/api/phase-b-vocabulary.openapi.yaml`](api/phase-b-vocabulary.openapi.yaml).

## Environment

- `OPENAI_API_KEY`: dedicated Quiz server credential. If absent or empty, both
  vocabulary operations return typed `503 provider_unavailable`; there is no
  fallback provider. It is the only permitted `OPENAI_*` process variable;
  tenant, project, admin, custom-header, base-URL, and SDK logging variables
  fail application settings validation before the OpenAI SDK is imported.
- `AI_MONTHLY_BUDGET_MICROUSD`: integer in `1..5000000`, default `5000000`.
  Configuration above US$5 fails application startup validation.

The model, voice, provider origin, paths, timeouts, token caps, and response
caps are code constants, not environment inputs. The provider client disables
ambient HTTP proxies, redirects, and SDK retries.

Lookup calculates one absolute 12-second deadline before durable daily work.
The same deadline is passed to the leader cache-miss provider task, so
coalescing and cancellation shielding cannot extend paid work or cache writes
beyond the leader's remaining budget.

Every reservation compares the configured monthly limit with the persisted
current-month row. A mismatch fails closed before a provider call; changing the
limit therefore requires an explicit, reviewed database reconciliation rather
than silently retaining a stale cap.

## Deploy and verification

1. Apply Alembic revision `f1b2c3d4e5a6`.
2. Insert the current UTC-month `ai_monthly_budgets` row with the configured
   limit and zero committed/reserved counters. The normal reservation path is
   also idempotent if the row already exists.
3. Deliver the dedicated credential through the approved non-model secret
   path. Never print it or place it in a client-visible variable.
4. Run `uv run --package quiz-backend python app/backend/check_ai_integrity.py`.
   The script verifies the credential is nonempty without printing it, the
   current budget row exists and matches configuration, counters are valid,
   and accounting/grant rows have no missing parents.
5. Run deterministic tests with the fake provider. A real-provider smoke is a
   separate approval gate; this change performs no paid call.

The four new tables all carry explicit constraints and timestamps. Expired
lookup grants are expected data and are not authorization: pronunciation
requires an unexpired grant owned by the current verified BetterAuth user.
