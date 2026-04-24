# URL Shortener Specification

## Overview

A personal, internal URL shortener that converts long URLs into short 7-character codes. Users identify themselves by username to view and manage their links. The system is not public-facing and has no authentication or access controls. It is deployed as two services: a Next.js frontend on Vercel and a FastAPI backend with a managed Postgres database on Railway.

---

## Goals and Non-Goals

### Goals
- Generate a unique 7-character short code for any valid HTTP/HTTPS URL
- Redirect short codes to their original long URLs
- Allow users to view all their active short links by username
- Automatically expire links 7 days after creation
- Provide a minimal browser-based UI for creating and viewing links

### Non-Goals
- Authentication or access control of any kind
- Click analytics or redirect tracking
- Custom or user-defined short codes
- Editing or deleting links after creation
- Public access or abuse prevention (rate limiting, CAPTCHA)
- Mobile-optimized UI
- Custom domain support

---

## Constraints

- **Scale:** tens of requests per second
- **Redirect latency:** no hard requirement — database lookup on every redirect is acceptable
- **Consistency:** eventual consistency is acceptable
- **Link lifetime:** 7 days from creation, then soft-expired and eventually hard-deleted
- **URL length:** maximum 2048 characters
- **Short code length:** exactly 7 characters, base-62 encoded
- **Cost:** free tier only — Vercel hobby plan, Railway free tier
- **Stack:** Python/FastAPI, Next.js, Postgres, deployed on Railway + Vercel

---

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│  Browser                                                 │
│                                                          │
│  GET /              ──────────────────────────────────▶ │ Next.js / Vercel
│  GET /dashboard?..  ──────────────────────────────────▶ │ (returns HTML + JS)
│                                                          │
│  GET /api/links?..  ──────────────────────────────────▶ │ FastAPI / Railway
│  POST /api/links    ──────────────────────────────────▶ │
│  GET /{short_code}  ──────────────────────────────────▶ │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────┐
│  Railway                    │
│  ┌──────────┐  ┌─────────┐  │
│  │ FastAPI  │──│Postgres │  │
│  └──────────┘  └─────────┘  │
└─────────────────────────────┘
```

### Components

**Next.js (Vercel)**
Serves the browser UI. Handles two routes: the home page (`/`) and the dashboard (`/dashboard`). Returns HTML and a JavaScript bundle on every page request. Has no knowledge of link data — all data fetching happens from the browser directly to FastAPI. Configured with one environment variable: `NEXT_PUBLIC_API_URL` pointing to the Railway FastAPI service.

**FastAPI (Railway)**
The backend service. Handles all three API operations: redirect, list links, create link. Talks directly to Postgres via SQLAlchemy. Runs an APScheduler background job that deletes expired rows hourly. Exposes no authentication layer.

**Postgres (Railway managed)**
Single database, single table: `links`. Source of truth for all link data. Accessed only by FastAPI via a connection string environment variable provided by Railway.

### Request Flows

**Page load**
```
Browser → GET / → Vercel → HTML + JS
Browser → GET /dashboard?user_id=roger → Vercel → HTML + JS
```
Vercel's involvement ends here. All subsequent requests go directly to Railway.

**Dashboard data fetch** (immediately after page load, initiated by JS in browser)
```
Browser → GET /api/links?user_id=roger → FastAPI → SELECT from Postgres → 200 JSON
```

**Create link**
```
Browser → POST /api/links {user_id, long_url} → FastAPI → INSERT ... RETURNING * → 201 JSON
```

**Redirect**
```
Browser → GET /{short_code} → FastAPI → SELECT from Postgres → 302 to long_url (or 404)
```
Next.js is not involved in this flow.

### Key Architectural Decisions

**Short code generation: base-62 encoding of auto-increment ID**
Each row in the links table has an integer primary key that auto-increments. The short code is the base-62 encoding of that integer, left-padded with zeros to 7 characters. Base-62 uses characters `[0-9A-Za-z]`. At 7 characters this yields 62^7 ≈ 3.5 trillion possible codes — sufficient for any realistic use. Collisions are impossible because the mapping from integer to code is deterministic and 1:1. Deleted rows do not decrement the counter, so codes are never reused.

Alternatives considered: UUID v4 (too long, overkill), hashing the ID (collision risk, no benefit for an internal system), random NanoID (requires collision checking).

**No cache**
At tens of requests per second, a single indexed Postgres table handles redirect lookups without a cache. Adding Redis would introduce operational complexity (cache invalidation, failure handling) with no meaningful latency improvement. Revisit if traffic grows significantly.

**Soft expiry + hourly hard delete**
On every redirect request, FastAPI checks `expires_at > NOW()` before redirecting. Expired links return 404 immediately without waiting for the cleanup job. A separate APScheduler job runs hourly inside the FastAPI process and hard-deletes rows where `expires_at < NOW()`. This means expired links are invisible to users immediately but rows are cleaned from the database within an hour. APScheduler was chosen over a request-counter-based trigger (fragile, stateful, resets on restart) and system cron (requires server access, more friction on Railway).

**No authentication**
Username is a plain string identifier with no password, session, or token. Two users entering the same username see the same links. This is acceptable for a personal internal tool where security is explicitly out of scope.

**Deployment split: Vercel + Railway**
Next.js on Vercel (familiar, purpose-built for Next.js, free tier sufficient). FastAPI on Railway (supports persistent processes, managed Postgres built in, free tier sufficient, no cold starts on hobby plan). The redirect endpoint lives on the Railway domain directly — no proxying through Vercel.

---

## Data Model

### Table: `links`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | integer | PRIMARY KEY, auto-increment | Never reused after deletion |
| `user_id` | varchar(255) | NOT NULL | Plain username string, no uniqueness constraint |
| `short_code` | varchar(7) | NOT NULL, UNIQUE | Base-62 encoding of `id`, left-padded to 7 chars |
| `long_url` | varchar(2048) | NOT NULL | Full URL including scheme |
| `created_at` | timestamptz | NOT NULL | Set at insert time, UTC |
| `expires_at` | timestamptz | NOT NULL | `created_at + 7 days`, UTC |

### Indexes
- Primary key on `id` (implicit)
- Unique index on `short_code` (redirect lookup path)
- Index on `user_id` (dashboard list lookup path)
- Index on `expires_at` (cleanup job efficiency)

### Short Code Generation

```
short_code = base62_encode(id).lstrip('0').rjust(7, '0')
```

Base-62 alphabet: `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz`

Example: `id=1` → `0000001`, `id=3521614606208` → `zzzzzzz`

---

## API Contract

### GET `/{short_code}`

Redirects to the long URL associated with the short code.

**Path parameter:** `short_code` — 7-character string

**Responses:**
- `302 Found` — redirect to `long_url`. Uses 302 (not 301) so browsers do not cache the redirect. Expired links must never be cached.
- `404 Not Found` — short code does not exist or link is expired (`expires_at < NOW()`)

**Behavior:** FastAPI checks both existence and expiry in a single query:
```sql
SELECT long_url FROM links WHERE short_code = $1 AND expires_at > NOW()
```

---

### GET `/api/links`

Returns all links for a given user.

**Query parameters:**
- `user_id` (required) — username string
- `include_expired` (optional, boolean, default `false`) — when `true`, includes expired links in results

**Responses:**

`200 OK` — always returns 200, even if the user has no links
```json
{
  "links": [
    {
      "short_code": "0000001",
      "long_url": "https://www.notion.so/some-page",
      "created_at": "2026-04-23T18:00:00Z",
      "expires_at": "2026-04-30T18:00:00Z"
    }
  ]
}
```

`400 Bad Request` — `user_id` is missing or empty/whitespace
```json
{ "error": "user_id is required" }
```

**Behavior:** When `include_expired=false` (default), filters with `AND expires_at > NOW()`. When `include_expired=true`, returns all rows for the user regardless of expiry.

---

### POST `/api/links`

Creates a new short link.

**Request body:**
```json
{
  "user_id": "roger",
  "long_url": "https://www.notion.so/some-page"
}
```

**Responses:**

`201 Created`
```json
{
  "short_code": "0000001",
  "long_url": "https://www.notion.so/some-page",
  "created_at": "2026-04-23T18:00:00Z",
  "expires_at": "2026-04-30T18:00:00Z"
}
```

`400 Bad Request` — any of the following:
```json
{ "error": "long_url is required" }
{ "error": "long_url must be a valid http or https URL" }
{ "error": "long_url must not exceed 2048 characters" }
{ "error": "user_id is required" }
```

**Behavior:** Validates inputs, inserts row, generates short_code from the returned `id` using base-62 encoding, updates the row with the generated `short_code`, returns the complete row. Uses `RETURNING *` to avoid a second SELECT.

---

## Behavior Specifications

### Link Creation

1. Trim `user_id` of leading/trailing whitespace. Reject if empty after trimming.
2. Validate `long_url`:
   - Must be present and non-empty
   - Must not exceed 2048 characters
   - Must be a structurally valid URL (parseable by standard URL parser)
   - Scheme must be `http` or `https` — reject `ftp://`, `javascript://`, `file://`, and all others
3. Insert row with `created_at = NOW()` and `expires_at = NOW() + INTERVAL '7 days'`
4. Use the returned `id` to generate `short_code` via base-62 encoding
5. Update the row with the generated `short_code`
6. Return `201` with the complete link object

### Redirect

1. Look up `short_code` in the database
2. If not found or `expires_at <= NOW()`: return `404`
3. If found and not expired: return `302` with `Location: {long_url}`

### Dashboard List

1. Validate `user_id` — reject if missing or empty/whitespace
2. Query links for `user_id`
3. If `include_expired=false`: filter to `expires_at > NOW()`
4. If `include_expired=true`: return all rows for user regardless of expiry
5. Return `200` with links array (empty array if none found — never 404 for unknown user)

### Expiry Cleanup Job

- Runs inside the FastAPI process using APScheduler
- Executes on server start and then every 1 hour
- Query: `DELETE FROM links WHERE expires_at < NOW()`
- Runs silently — no user-facing behavior. Failures are logged but do not affect request handling.

---

## Frontend Specification

### Page: `/` (Home)

A single input field for username and a submit button. On submit: trim the username, reject empty strings with an inline error message, navigate to `/dashboard?user_id={username}` on valid input. No server interaction on this page.

**States:**
- Default — empty input
- Error — empty username submitted, show inline error "Username is required"

### Page: `/dashboard?user_id={username}`

Displays the username at the top. Shows a form to create a new link. Shows a list of the user's links. Shows a toggle to include expired links (off by default).

**On page load:** fetch `GET /api/links?user_id={username}` and render results.

**Create link form:** single text input for `long_url`, submit button. On submit: call `POST /api/links`, on success prepend new link to the list, on failure show inline error message from API response.

**Link list columns:** short code (as a clickable anchor tag linking to the Railway redirect URL), long URL (truncated to 60 characters with ellipsis if longer), expires at (formatted as `MMM DD, YYYY`).

**Expired links toggle:** when enabled, re-fetches `GET /api/links?user_id={username}&include_expired=true` and re-renders the list. Expired links are visually distinguished (greyed out).

**States:**
- Loading — fetching links on page load
- Empty — user has no links, show "No links yet" message
- Populated — list of links
- Error — API unreachable, show "Failed to load links" message

### Environment Variables

| Variable | Used by | Value |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Next.js (browser) | Railway FastAPI public URL |
| `DATABASE_URL` | FastAPI | Railway Postgres connection string |

---

## Failure Modes

**Postgres unavailable**
- Redirect requests: FastAPI returns `500`. User sees an error page.
- List/create requests: FastAPI returns `500`. UI shows error state.
- Cleanup job: logs error, skips the run, retries on next scheduled interval.

**FastAPI unavailable**
- Page loads still work — Vercel serves the UI shell.
- Data fetches fail — dashboard shows error state.
- Redirects fail — user sees Railway error page.

**Short code not found**
- Return `404`. No distinction between "never existed" and "expired" in the response — both are `404`.

**Invalid URL submitted**
- Return `400` with specific error message. No row is inserted.

**APScheduler job failure**
- Soft expiry on redirect ensures users never see expired links regardless.
- Hard delete will retry on next hourly run.
- Log the error with timestamp and exception detail.

---

## Security

No authentication or access control is implemented. This is explicitly out of scope for this system. The following minimal measures apply:

**URL scheme validation:** Only `http` and `https` schemes are accepted as `long_url`. This prevents `javascript:` URI injection where a browser might execute script when following a redirect.

**Input trimming and validation:** `user_id` is trimmed and rejected if empty. `long_url` is validated structurally before insert.

**No sensitive data:** No passwords, tokens, or PII are stored. The only user-supplied data is a plain username string and URLs.

**Threat model:** The system is personal and internal. No abuse prevention (rate limiting, CAPTCHA) is implemented. If exposed publicly, this would need to be revisited.

---

## Observability

### Logging
- Every redirect: log `short_code`, result (`302` or `404`), timestamp
- Every link creation: log `user_id`, `short_code`, `long_url` (truncated), timestamp
- Every validation failure: log reason and input (truncate `long_url` to 100 chars)
- Cleanup job: log count of deleted rows on each run, log errors if job fails

### No alerting required for this project.

---

## Test Cases

### Happy Path

**TC-01 Create link — valid input**
POST `/api/links` with valid `user_id` and valid `https://` URL. Expect `201` with `short_code` of exactly 7 characters, `long_url` matching input, `expires_at` approximately 7 days after `created_at`.

**TC-02 Redirect — valid active link**
GET `/{short_code}` for an existing, non-expired link. Expect `302` redirect to correct `long_url`.

**TC-03 List links — existing user**
GET `/api/links?user_id=roger` for a user with active links. Expect `200` with non-empty links array.

**TC-04 List links — unknown user**
GET `/api/links?user_id=nobody` for a user with no links. Expect `200` with empty links array.

**TC-05 Short codes are sequential and unique**
Create 3 links in order. Expect short codes to be distinct base-62 encodings of sequential integers.

### Expiry

**TC-06 Redirect — expired link**
GET `/{short_code}` for a link where `expires_at` is in the past. Expect `404`.

**TC-07 List links — expired links excluded by default**
User has both active and expired links. GET `/api/links?user_id=roger`. Expect only active links in response.

**TC-08 List links — include_expired=true**
Same user. GET `/api/links?user_id=roger&include_expired=true`. Expect both active and expired links in response.

**TC-09 Cleanup job deletes expired rows**
Insert a link with `expires_at` in the past. Trigger cleanup job. Query database directly — expect row to be gone.

### Validation

**TC-10 Create link — missing long_url**
POST with `user_id` only. Expect `400` with error message.

**TC-11 Create link — invalid URL scheme**
POST with `long_url = "javascript:alert(1)"`. Expect `400`.

**TC-12 Create link — ftp scheme rejected**
POST with `long_url = "ftp://files.example.com/file.txt"`. Expect `400`.

**TC-13 Create link — URL exceeds 2048 characters**
POST with `long_url` of 2049 characters. Expect `400`.

**TC-14 Create link — URL of exactly 2048 characters**
POST with `long_url` of exactly 2048 characters (valid http URL). Expect `201`.

**TC-15 Create link — empty user_id**
POST with `user_id = ""`. Expect `400`.

**TC-16 Create link — whitespace-only user_id**
POST with `user_id = "   "`. Expect `400`.

**TC-17 List links — missing user_id**
GET `/api/links` with no `user_id` parameter. Expect `400`.

### Redirect Behavior

**TC-18 Redirect uses 302 not 301**
GET `/{short_code}`. Expect response status is exactly `302`, not `301`.

**TC-19 Redirect — nonexistent short code**
GET `/0000000` where no such code exists. Expect `404`.

### Short Code Generation

**TC-20 First link produces short code `0000001`**
On a fresh database, create the first link. Expect `short_code = "0000001"`.

**TC-21 Short code is always exactly 7 characters**
Create links until `id` exceeds single-digit range. All short codes are exactly 7 characters.

---

## Open Questions

None. All decisions are resolved.

---

## Out of Scope

- Click tracking or analytics
- Custom/vanity short codes
- Editing or deleting links after creation
- User authentication or passwords
- Rate limiting or abuse prevention
- Link expiry reset on access
- Admin interface
- API keys or programmatic access control
- Custom domains
- Mobile-optimized UI
- Email notifications
- Bulk link creation
