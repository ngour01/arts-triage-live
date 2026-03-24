-- ART v3 Relational Triage Schema (Definitive Version)
DROP TABLE IF EXISTS run_stats_snapshots CASCADE;
DROP TABLE IF EXISTS triage_signals CASCADE;
DROP TABLE IF EXISTS error_patterns CASCADE;
DROP TABLE IF EXISTS test_attempts CASCADE;
DROP TABLE IF EXISTS test_executions CASCADE;
DROP TABLE IF EXISTS runs CASCADE;
DROP TABLE IF EXISTS master_rules CASCADE;
DROP TABLE IF EXISTS buckets CASCADE;

-- 1. Metadata Buckets
CREATE TABLE buckets (
    id INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    is_sticky BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

-- 2. Triage Intelligence (Rules)
CREATE TABLE master_rules (
    id SERIAL PRIMARY KEY,
    pattern_text TEXT UNIQUE NOT NULL, 
    target_bucket_id INTEGER REFERENCES buckets(id),
    added_by VARCHAR(100) DEFAULT 'System',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

-- 3. Execution Containers
CREATE TABLE runs (
    id SERIAL PRIMARY KEY,
    identifier VARCHAR(100) UNIQUE NOT NULL, 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE TABLE test_executions (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
    feature_name VARCHAR(255),
    test_case_name VARCHAR(255),
    latest_attempt_number INTEGER DEFAULT 0,
    is_currently_passing BOOLEAN DEFAULT FALSE,
    has_sticky_failure BOOLEAN DEFAULT FALSE,
    latest_bucket_id INTEGER REFERENCES buckets(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    UNIQUE(run_id, feature_name, test_case_name)
);

-- 4. Attempt History
CREATE TABLE test_attempts (
    id SERIAL PRIMARY KEY,
    test_execution_id INTEGER REFERENCES test_executions(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL,
    log_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

-- 5. Knowledge Base & Signals
CREATE TABLE error_patterns (
    fingerprint VARCHAR(64) PRIMARY KEY,
    scrubbed_message TEXT,
    error_class VARCHAR(100),
    resolved_bucket_id INTEGER REFERENCES buckets(id),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE TABLE triage_signals (
    id SERIAL PRIMARY KEY,
    test_attempt_id INTEGER REFERENCES test_attempts(id) ON DELETE CASCADE,
    fingerprint VARCHAR(64) REFERENCES error_patterns(fingerprint) ON DELETE CASCADE,
    bug_id VARCHAR(50),
    deleted_at TIMESTAMP,
    UNIQUE(test_attempt_id, fingerprint)
);

-- 6. Statistics Snapshots
CREATE TABLE run_stats_snapshots (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
    bucket_id INTEGER REFERENCES buckets(id),
    feature_count INTEGER DEFAULT 0,
    suite_count INTEGER DEFAULT 0,
    test_count INTEGER DEFAULT 0,
    pr_count INTEGER DEFAULT 0,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    UNIQUE(run_id, bucket_id)
);

-- Initial Metadata Seed
INSERT INTO buckets (id, name, is_sticky) VALUES
(1, 'User Errors', FALSE),
(2, 'Infra Errors', FALSE),
(3, 'Product (PSOD)', TRUE),
(4, 'Unknown', FALSE),
(5, 'Test Logic', FALSE),
(6, 'Timeouts', FALSE);

-- Performance Indexes
CREATE INDEX idx_test_executions_run_id ON test_executions(run_id);
CREATE INDEX idx_test_attempts_execution_id ON test_attempts(test_execution_id);
CREATE INDEX idx_test_attempts_log_url ON test_attempts(log_url);
CREATE INDEX idx_triage_signals_attempt_id ON triage_signals(test_attempt_id);
CREATE INDEX idx_error_patterns_bucket_id ON error_patterns(resolved_bucket_id);
CREATE INDEX idx_run_stats_run_id ON run_stats_snapshots(run_id);

-- Prevent duplicate log_url entries across concurrent crawlers
CREATE UNIQUE INDEX idx_test_attempts_unique_log_url ON test_attempts(log_url) WHERE log_url IS NOT NULL;
