-- Schema exported from packaged application/backend/workflow.sqlite

CREATE TABLE approvals (key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL);

CREATE TABLE cases (id TEXT PRIMARY KEY, payload TEXT NOT NULL);

CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
