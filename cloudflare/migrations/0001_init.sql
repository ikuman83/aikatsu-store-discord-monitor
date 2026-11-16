CREATE TABLE IF NOT EXISTS store_state (
  name TEXT PRIMARY KEY NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('present','absent')),
  missing_count INTEGER NOT NULL DEFAULT 0,
  checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS machine_state (
  id TEXT PRIMARY KEY NOT NULL,
  store TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  sent_at TEXT
);
CREATE INDEX IF NOT EXISTS notifications_pending ON notifications(sent_at,created_at);
CREATE TABLE IF NOT EXISTS scan_lease (
  key TEXT PRIMARY KEY NOT NULL,
  token TEXT NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS health (
  key TEXT PRIMARY KEY NOT NULL,
  value TEXT NOT NULL
);

-- Seed known listing presence from the last verified GitHub checks.
-- As of Nov 15, Bic Camera had been absent and the other three present.
INSERT OR IGNORE INTO store_state(name,status,missing_count,checked_at) VALUES
 ('タイトーステーション 国分寺店','present',0,'2026-11-14T22:55:39Z'),
 ('タイトーステーション 立川北口店','present',0,'2026-11-14T22:55:39Z'),
 ('namcoららぽーと立川立飛おまけ横丁店','present',0,'2026-11-14T22:55:39Z'),
 ('ビックカメラ立川店','absent',2,'2026-11-14T22:55:39Z');
