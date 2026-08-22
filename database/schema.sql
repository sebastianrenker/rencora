-- database/schema.sql — RENCORA persistentes Datenmodell (Teil 11 des
-- Architektur-Reviews). Ergaenzt die bestehenden flachen JSON-Dateien
-- (long_term.json, people.json, second_brain.json) um strukturierte,
-- abfragbare Tabellen fuer Projekte, Aufgaben, Entscheidungen, Wissen,
-- Events und Agenten-Laeufe. Migration erfolgt im Dual-Write-Verfahren:
-- bestehende JSON-Dateien bleiben unangetastet, SQLite laeuft parallel
-- mit, bis der neue Pfad verifiziert ist (kein harter Cutover).

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('active','paused','done','archived')) DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    description TEXT NOT NULL,
    target_date TEXT,
    status TEXT CHECK(status IN ('open','in_progress','done','dropped')) DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER REFERENCES goals(id),
    description TEXT NOT NULL,
    agent TEXT,
    status TEXT CHECK(status IN ('pending','running','done','failed')) DEFAULT 'pending',
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id),
    reasoning TEXT NOT NULL,
    alternatives_considered TEXT,
    made_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY,
    source_type TEXT,            -- 'second_brain' | 'whatsapp' | 'manual'
    source_ref TEXT,             -- z.B. second_brain.json entry id
    summary TEXT,
    embedding BLOB,               -- optionaler Vektor, spaeter fuer semantische Suche
    tags TEXT,                    -- JSON-Array als Text
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    category TEXT NOT NULL,       -- identity|preferences|projects|relationships|wishes|notes
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(category, key)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,     -- 'mail.important' | 'calendar.upcoming' | ...
    payload TEXT,                 -- JSON
    occurred_at TEXT NOT NULL,
    handled INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY,
    level TEXT,
    module TEXT,
    message TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY,
    agent TEXT NOT NULL,
    tool_name TEXT,
    params TEXT,                  -- JSON, entspricht fc.args in main.py::_execute_tool
    result TEXT,
    status TEXT CHECK(status IN ('success','failed')),
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent);

-- Nutzerseitige Aufgaben/Automatisierung (Teil 9): eigenstaendig von den
-- ziel-gebundenen internen `tasks`. Traegt Subtasks (parent_id), Prioritaet,
-- Abhaengigkeiten (depends_on) und Wiederholung.
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    details TEXT,
    status TEXT CHECK(status IN ('pending','active','blocked','done','cancelled')) DEFAULT 'pending',
    priority INTEGER DEFAULT 1,               -- 0 niedrig .. 3 dringend
    parent_id INTEGER REFERENCES todos(id),   -- Subtask-Verknuepfung
    depends_on INTEGER REFERENCES todos(id),  -- muss zuerst erledigt sein
    due_at TEXT,
    recurrence TEXT,                          -- 'daily' | 'weekly' | NULL
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    done_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
CREATE INDEX IF NOT EXISTS idx_todos_parent ON todos(parent_id);
