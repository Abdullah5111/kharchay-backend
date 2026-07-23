# Kharchay — Backend

> **Kharchay** (خرچے, Urdu for *“expenses”*) is a shared-household expense & **mess-management** app for homes and hostels — people who split rent and bills *and* run a common kitchen. This repo is the **REST API** that powers it.

The companion mobile app lives in **[kharchay-frontend](https://github.com/Abdullah5111/kharchay-frontend)** (Expo / React Native).

---

## What it does

Members record shared spending and daily meal attendance; the app computes **who owes whom** at month-end, and members submit manual payments (with proof) that admins approve. Each group has two sides:

- **My Expenses** — personal: standing, activity, meal history, payments, notifications.
- **Management** *(admins)* — record expenses, mark attendance, run settlement, approve payments.

### Feature domains

| Domain | What it covers |
| --- | --- |
| **Accounts** | Passwordless **email-OTP → JWT** sign-in (SimpleJWT), custom email user, device-token registration for push. |
| **Social** | Friend requests, groups, memberships with roles (`owner`/`admin`/`member`); friend-gated group invites. |
| **Ledger** | Monthly Expenses, Kitchen Expenses, Workplace Items — equal/custom split, per-month finalization lock. |
| **Haazri** | Daily meal attendance per kitchen pool, with guest multipliers and per-event extra amounts. |
| **Settlement** | Per-pool kitchen division (`spend ÷ units × member units`) + extras + net **“who owes whom”**, minimized transfers. |
| **Payments** | Manual payment submission with **proof image** upload, admin approve/reject, payer notifications. |
| **Notifications** | In-app feed + best-effort Expo push (meal marked, period finalized, settlement ready, payment approved/rejected, …). |

---

## Tech stack

- **Python 3.12 · Django 5.0** · **Django REST Framework 3.15** · **SimpleJWT**
- **PostgreSQL 16** (via `psycopg` 3) · **Redis** + **Celery** (async email/push/settlement)
- **Payment-proof storage** — Django `FileSystemStorage` under `MEDIA_ROOT`, bind-mounted to the host and served by nginx (see the `14labs-infra` deploy)
- **Gunicorn**, fully **Dockerized** (`docker compose`)
- **pytest-django** test suite (**173 tests**)

---

## Project structure

```
.
├── config/            # settings, root urls, celery app, wsgi
├── manage.py
├── Dockerfile
└── apps/
    ├── core/          # health check, shared utilities
    ├── accounts/      # email-OTP auth, JWT, custom user, device tokens
    ├── social/        # friendships, groups, memberships, permissions
    ├── ledger/        # categories, expenses, shares, period finalization, split logic
    ├── haazri/        # meal events, attendance (+ guests), extras, disputes, summary
    ├── settlement/    # compute engine, transfer minimization, standing & activity
    ├── payments/      # Payment model, proof storage, submit/approve/reject
    └── notifications/ # notification feed + Expo push tasks
```

---

## Getting started

### Option A — Docker (recommended)

Brings up Postgres, Redis, the API, and a Celery worker.

```bash
cp .env.example .env          # then fill in the secrets (see table below)
docker network create services-net   # one-time, shared external network
docker compose up --build
```

The API is served on **http://127.0.0.1:8020** (health check: `GET /api/health/`). The `web` service runs migrations automatically on start.

### Option B — Local (for development & tests)

The test suite runs against **SQLite** with no external services, so it needs only a virtualenv:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 0.0.0.0:8020
```

### Environment variables

Configured via `django-environ`; see [`.env.example`](.env.example).

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django secret (generate a strong random value for production). |
| `DEBUG` | `False` in production. |
| `ALLOWED_HOSTS` | Comma-separated allowed hostnames. |
| `DATABASE_URL` | Postgres DSN (`postgres://user:pass@db:5432/name`). |
| `REDIS_URL` | Redis URL for Celery broker/result backend. |
| `MEDIA_ROOT` | Filesystem path for payment-proof uploads (bind-mounted to the host; defaults to `BASE_DIR/media`). |
| `EMAIL_*` / `DEFAULT_FROM_EMAIL` | SMTP settings for OTP delivery (console backend by default in dev). |

---

## API overview

Auth: `Authorization: Bearer <access>` (JWT). All write endpoints enforce group membership and role checks.

```
Auth        POST /api/auth/request-otp · verify-otp · complete-profile · refresh · /api/devices
Me/Friends  GET/PATCH /api/me · /api/friends · /api/friends/requests[/{id}/accept|reject]
Groups      GET/POST /api/groups · /api/groups/{id}[/members[/{uid}/role]] · invites accept/reject
Ledger      GET/POST /api/groups/{id}/expenses · PATCH/DELETE /api/expenses/{id} · periods/finalize
Haazri      GET/POST /api/groups/{id}/haazri · PUT /api/haazri/{event}/attendance · extras · dispute
Settlement  GET /api/groups/{id}/settlement · POST .../{year}/{month}/generate · GET /api/me/standing · /api/me/activity
Payments    GET/POST /api/groups/{id}/payments · POST /api/payments/{id}/approve|reject · GET /api/me/payments
Notifs      GET /api/notifications · POST /api/notifications/read
```

---

## Testing

```bash
.venv/bin/python -m pytest          # Windows: .venv\Scripts\python -m pytest
```

The suite (173 tests) covers auth, permissions, the money invariants (e.g. **settlement nets sum to zero**, splits sum exactly to the amount), the file-upload path, and the status machines.

---

## Settlement, in one paragraph

For each kitchen pool in a month: `pool_rate = pool_spend / total_attendance_units`, and each member owes `rate × their units` (last share absorbs the rounding remainder so the books balance to the paisa). Add each member’s expense shares and extra-amount shares, subtract what they paid, and you get their **net** (positive = owes). A greedy creditor/debtor match turns all the nets into the **minimum set of transfers** that settles everyone.

---

## Status & roadmap

**Feature-complete** across auth → social → ledger → Haazri → settlement → payments.

Payment-proof images are validated by **magic-byte sniffing** (not just the
client-supplied content-type) and stored via Django `FileSystemStorage`, served
by nginx under `/media/` with `X-Content-Type-Options: nosniff` and
`Content-Disposition: attachment`.

Optional future hardening (not required for the internal APK build):

- Move payment-proof storage to **S3/MinIO with signed URLs** (or an
  authenticated download view) if proofs ever need to be private per-user rather
  than served via unguessable `uuid4` capability links.

---

## Related

- 📱 Mobile app: **[kharchay-frontend](https://github.com/Abdullah5111/kharchay-frontend)**

## License

No license has been assigned yet — all rights reserved by the author.
