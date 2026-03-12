-- Script de création de la base de données SQLite
-- Système Distribué de Supervision Réseau
-- UN-CHK M1 SRIV Promo 2025

-- Table des nœuds supervisés
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT UNIQUE NOT NULL,
    os TEXT,
    cpu_type TEXT,
    last_seen TEXT,
    status TEXT DEFAULT 'ACTIVE'  -- ACTIVE | DOWN
);

-- Table des métriques collectées
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    cpu REAL,         -- Charge CPU en %
    memory REAL,      -- Charge mémoire en %
    disk REAL,        -- Charge disque en %
    uptime INTEGER,   -- Uptime en secondes
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (node_id) REFERENCES nodes(node_id)
);

-- Table des statuts de services
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_id INTEGER,
    node_id TEXT,
    service_name TEXT,  -- http, ssh, ftp, firefox, chrome, vlc
    status TEXT,        -- OK | DOWN
    timestamp TEXT,
    FOREIGN KEY (metric_id) REFERENCES metrics(id)
);

-- Table des statuts de ports
CREATE TABLE IF NOT EXISTS ports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_id INTEGER,
    node_id TEXT,
    port INTEGER,       -- 80, 22, 443, 3306
    status TEXT,        -- OPEN | CLOSED
    timestamp TEXT,
    FOREIGN KEY (metric_id) REFERENCES metrics(id)
);

-- Table des alertes
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT,
    message TEXT,
    timestamp TEXT DEFAULT (datetime('now')),
    resolved INTEGER DEFAULT 0
);

-- Table des logs
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT,    -- INFO | ALERT | DOWN
    message TEXT,
    timestamp TEXT DEFAULT (datetime('now'))
);

-- Index pour performances
CREATE INDEX IF NOT EXISTS idx_metrics_node ON metrics(node_id);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_node ON alerts(node_id);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
