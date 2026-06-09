-- AI Income Team — SQLite schema.
-- IMPORTANT: the `sales` table is the ONLY source of revenue numbers, and it is
-- written exclusively from real platform data by the bookkeeper agent. There is
-- no demo/seed data path anywhere in this app, so with no real sales the
-- dashboard truthfully shows $0.

-- Generic key/value app settings (PIN hash, first-run flags, tunnel url, etc.)
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- The agent roster shown on the dashboard.
CREATE TABLE IF NOT EXISTS agents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,          -- internal id, e.g. "pod"
    display_name TEXT NOT NULL,                 -- human label
    description  TEXT,
    enabled      INTEGER NOT NULL DEFAULT 0,    -- 0/1
    status       TEXT NOT NULL DEFAULT 'idle',  -- idle|running|waiting_approval|error
    last_run_at  TEXT
);

-- Everything every agent does. Streamed live to the dashboard ("see EVERYTHING").
CREATE TABLE IF NOT EXISTS activity_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent        TEXT NOT NULL,
    level        TEXT NOT NULL DEFAULT 'info',  -- info|success|warn|error
    message      TEXT NOT NULL,
    payload_json TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Human-in-the-loop gate. No publish/post/money/brand action fires without an
-- approved row here. Pending rows survive restarts (fail-safe by default).
CREATE TABLE IF NOT EXISTS approvals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent        TEXT NOT NULL,
    action_type  TEXT NOT NULL,   -- pod_publish|digital_publish|video_publish|social_post|payout_action
    title        TEXT NOT NULL,
    summary      TEXT,
    payload_json TEXT,            -- resumable context for the suspended task
    preview_url  TEXT,            -- image/video/asset preview for the approval card
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|expired
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at  TEXT,
    resolved_by  TEXT
);

-- Products created across all streams.
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    stream      TEXT NOT NULL,                  -- pod|digital|video
    platform    TEXT,
    external_id TEXT,
    title       TEXT,
    status      TEXT NOT NULL DEFAULT 'draft',  -- draft|pending_approval|live|rejected
    meta_json   TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- REAL sales only. external_id is unique to make ingestion idempotent.
CREATE TABLE IF NOT EXISTS sales (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER,
    platform    TEXT NOT NULL,
    external_id TEXT UNIQUE,
    gross_amount REAL NOT NULL DEFAULT 0,
    fees        REAL NOT NULL DEFAULT 0,
    net_amount  REAL NOT NULL DEFAULT 0,
    currency    TEXT NOT NULL DEFAULT 'USD',
    occurred_at TEXT,
    source      TEXT
);

-- Which external services the user has connected (the secret VALUE lives in the
-- encrypted vault / OS keyring, never here).
CREATE TABLE IF NOT EXISTS secrets_meta (
    service      TEXT PRIMARY KEY,
    is_connected INTEGER NOT NULL DEFAULT 0,
    connected_at TEXT
);

-- Local tracking of free-tier usage so the app can self-throttle.
CREATE TABLE IF NOT EXISTS quota_usage (
    service    TEXT NOT NULL,
    day        TEXT NOT NULL,
    units_used INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (service, day)
);

-- Demand/trend research briefs that steer WHAT the agents create. Synthesized by
-- the brain from FREE best-effort signals (Google Trends RSS, Reddit). These are
-- guidance only — they never publish, post, or spend.
CREATE TABLE IF NOT EXISTS demand_briefs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,            -- e.g. trends+reddit | brain_only | optimizer
    niche         TEXT,
    audience      TEXT,
    product_angle TEXT,
    keywords_json TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Plain-language reports the optimizer writes from REAL sales ("what's working").
CREATE TABLE IF NOT EXISTS reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,               -- e.g. optimizer
    title      TEXT NOT NULL,
    body       TEXT,
    data_json  TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- SEO blog posts (free organic traffic). Published posts are served on the public
-- /blog and can be exported as static HTML. Approved by you before going live.
CREATE TABLE IF NOT EXISTS blog_posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    summary       TEXT,
    body_html     TEXT,
    keywords_json TEXT,
    product_id    INTEGER,
    status        TEXT NOT NULL DEFAULT 'draft',   -- draft|published
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    published_at  TEXT
);

-- Email list captured from the public blog (an owned audience you can promote to).
-- The newsletter agent drafts broadcasts; you send them from your own email tool.
CREATE TABLE IF NOT EXISTS email_subscribers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT UNIQUE NOT NULL,
    source     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
