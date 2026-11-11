-- 班级 Deadline 中心 · SQLite schema v1
-- 约定：时间一律存 UTC ISO8601 字符串（秒级），由应用层负责转换。
-- 所有语句幂等，可重复执行。

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS classes (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  college      TEXT NOT NULL DEFAULT '',
  major        TEXT NOT NULL DEFAULT '',
  grade        TEXT NOT NULL DEFAULT '',
  invite_code  TEXT NOT NULL UNIQUE,
  created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  class_id      INTEGER NOT NULL REFERENCES classes(id),
  student_no    TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'student'
                CHECK (role IN ('student','monitor','secretary','admin')),
  status        TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','active','disabled')),
  password_hash TEXT NOT NULL,
  must_change_password INTEGER NOT NULL DEFAULT 0,
  avatar        TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL,
  last_login_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_class ON users(class_id, status);

CREATE TABLE IF NOT EXISTS deadlines (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  class_id      INTEGER NOT NULL REFERENCES classes(id),
  title         TEXT NOT NULL,
  summary       TEXT NOT NULL DEFAULT '',
  category      TEXT NOT NULL
                CHECK (category IN ('homework','form','task','exam')),
  audience      TEXT NOT NULL DEFAULT 'class'
                CHECK (audience IN ('class','committee')),
  course        TEXT NOT NULL DEFAULT '',
  due_at        TEXT,
  due_at_raw    TEXT NOT NULL DEFAULT '',
  all_day       INTEGER NOT NULL DEFAULT 0,
  location      TEXT NOT NULL DEFAULT '',
  link          TEXT NOT NULL DEFAULT '',
  attachments   TEXT NOT NULL DEFAULT '[]',
  source_type   TEXT NOT NULL DEFAULT 'manual'
                CHECK (source_type IN ('manual','qq','paste','bookmarklet','chaoxing','yuketang','import')),
  source_ref    TEXT NOT NULL DEFAULT '',
  status        TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft','published','archived')),
  confidence    REAL,
  needs_review  INTEGER NOT NULL DEFAULT 0,
  dedupe_key    TEXT,
  subtype       TEXT,
  task_level    TEXT,
  created_by    INTEGER REFERENCES users(id),
  reviewed_by   INTEGER REFERENCES users(id),
  published_at  TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dl_class_due ON deadlines(class_id, status, due_at);
CREATE INDEX IF NOT EXISTS idx_dl_class_aud ON deadlines(class_id, audience, status, due_at);
CREATE INDEX IF NOT EXISTS idx_dl_dedupe    ON deadlines(class_id, dedupe_key);

CREATE TABLE IF NOT EXISTS completions (
  deadline_id INTEGER NOT NULL REFERENCES deadlines(id) ON DELETE CASCADE,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  state       TEXT NOT NULL DEFAULT 'done' CHECK (state IN ('done','skip')),
  note        TEXT NOT NULL DEFAULT '',
  updated_at  TEXT NOT NULL,
  PRIMARY KEY (deadline_id, user_id)
);

-- 指定参与人：有记录时，班级事项只对这些人生效（班委仍可见）。
CREATE TABLE IF NOT EXISTS deadline_targets (
  deadline_id INTEGER NOT NULL REFERENCES deadlines(id) ON DELETE CASCADE,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  PRIMARY KEY (deadline_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_dl_targets_user ON deadline_targets(user_id);

CREATE TABLE IF NOT EXISTS sources (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  class_id    INTEGER NOT NULL REFERENCES classes(id),
  type        TEXT NOT NULL,
  name        TEXT NOT NULL DEFAULT '',
  config      TEXT NOT NULL DEFAULT '{}',
  enabled     INTEGER NOT NULL DEFAULT 1,
  token_hash  TEXT,
  last_ok_at  TEXT,
  last_error  TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_class ON sources(class_id, type);

CREATE TABLE IF NOT EXISTS raw_messages (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id     INTEGER NOT NULL REFERENCES sources(id),
  external_id   TEXT,
  sender_name   TEXT NOT NULL DEFAULT '',
  sender_id     TEXT NOT NULL DEFAULT '',
  chat_name     TEXT NOT NULL DEFAULT '',
  content       TEXT NOT NULL,
  attachments   TEXT NOT NULL DEFAULT '[]',
  occurred_at   TEXT NOT NULL,
  ingested_at   TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new','extracted','ignored','failed')),
  UNIQUE (source_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_status ON raw_messages(status, ingested_at);

CREATE TABLE IF NOT EXISTS extraction_jobs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_message_id  INTEGER REFERENCES raw_messages(id),
  provider        TEXT NOT NULL,
  model           TEXT NOT NULL DEFAULT '',
  prompt_version  TEXT NOT NULL DEFAULT 'v1',
  output          TEXT NOT NULL DEFAULT '',
  parsed          TEXT NOT NULL DEFAULT '{}',
  confidence      REAL,
  status          TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','failed','invalid')),
  error           TEXT NOT NULL DEFAULT '',
  human_fix       TEXT NOT NULL DEFAULT '{}',
  created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_msg ON extraction_jobs(raw_message_id);

CREATE TABLE IF NOT EXISTS revisions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  deadline_id INTEGER NOT NULL REFERENCES deadlines(id) ON DELETE CASCADE,
  actor_id    INTEGER REFERENCES users(id),
  action      TEXT NOT NULL,
  before      TEXT NOT NULL DEFAULT '{}',
  after       TEXT NOT NULL DEFAULT '{}',
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rev_dl ON revisions(deadline_id, created_at);

CREATE TABLE IF NOT EXISTS notifications (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES users(id),
  deadline_id  INTEGER REFERENCES deadlines(id) ON DELETE CASCADE,
  channel      TEXT NOT NULL DEFAULT 'web',
  kind         TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,
  sent_at      TEXT,
  status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','failed','skipped')),
  class_id     INTEGER,
  title        TEXT NOT NULL DEFAULT '',
  body         TEXT NOT NULL DEFAULT '',
  read_at      TEXT,
  UNIQUE (user_id, deadline_id, kind, channel)
);

CREATE TABLE IF NOT EXISTS personal_items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  class_id   INTEGER NOT NULL,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title      TEXT NOT NULL,
  note       TEXT NOT NULL DEFAULT '',
  due_at     TEXT,
  done       INTEGER NOT NULL DEFAULT 0,
  client_key TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_personal_user ON personal_items(user_id, done);

CREATE TABLE IF NOT EXISTS sessions (
  id         TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf       TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  ua         TEXT NOT NULL DEFAULT '',
  ip         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS audit_logs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_id   INTEGER,
  action     TEXT NOT NULL,
  target     TEXT NOT NULL DEFAULT '',
  meta       TEXT NOT NULL DEFAULT '{}',
  ip         TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at);

CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
