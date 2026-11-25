CREATE TABLE IF NOT EXISTS machine_online_state (
  id TEXT PRIMARY KEY NOT NULL,
  store TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('online','offline')),
  checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS machine_online_by_store ON machine_online_state(store);
