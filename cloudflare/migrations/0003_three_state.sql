-- Separate table avoids interrupting live readers during three-state migration.
CREATE TABLE IF NOT EXISTS machine_status_v2 (
  id TEXT PRIMARY KEY NOT NULL,
  store TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('online','offline','card_empty')),
  checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS machine_status_v2_by_store ON machine_status_v2(store);
INSERT OR IGNORE INTO machine_status_v2(id,store,status,checked_at)
SELECT id,store,status,checked_at
FROM machine_online_state
WHERE status IN ('online','offline');
