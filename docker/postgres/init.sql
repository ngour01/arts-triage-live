-- ARTs v1.0.0 — Partitioned Production Schema
-- Auto-executed on first `docker compose up` via entrypoint

-- 1. DROP OLD TABLES (Clean start)
DROP TABLE IF EXISTS triage_signals CASCADE;
DROP TABLE IF EXISTS error_patterns CASCADE;
DROP TABLE IF EXISTS test_attempts CASCADE;
DROP TABLE IF EXISTS test_executions CASCADE;
DROP TABLE IF EXISTS runs CASCADE;
DROP TABLE IF EXISTS master_rules CASCADE;
DROP TABLE IF EXISTS buckets CASCADE;

-- 2. BUCKETS (The Categories)
CREATE TABLE buckets (
    id INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    is_sticky BOOLEAN DEFAULT FALSE
);

INSERT INTO buckets (id, name, is_sticky) VALUES
(1, 'User Errors',    FALSE),
(2, 'Infra Errors',   FALSE),
(3, 'Product (PSOD)', TRUE),
(4, 'Unknown',        FALSE),
(5, 'Test Logic',     FALSE),
(6, 'Timeouts',       FALSE);

-- 3. MASTER RULES (The Brain)
CREATE TABLE master_rules (
    id SERIAL PRIMARY KEY,
    pattern_text TEXT UNIQUE NOT NULL,
    target_bucket_id INTEGER REFERENCES buckets(id),
    specific_action VARCHAR(255),
    added_by VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. RUNS (Cycle tracking)
CREATE TABLE runs (
    id SERIAL PRIMARY KEY,
    run_type VARCHAR(20) NOT NULL,
    identifier VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(50),
    total_tests INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. TEST EXECUTIONS
CREATE TABLE test_executions (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
    feature_name VARCHAR(255) NOT NULL,
    test_case_name VARCHAR(255) NOT NULL,
    latest_attempt_number INTEGER DEFAULT 0,
    is_currently_passing BOOLEAN DEFAULT FALSE,
    has_sticky_failure BOOLEAN DEFAULT FALSE,
    latest_bucket_id INTEGER REFERENCES buckets(id),
    UNIQUE(run_id, feature_name, test_case_name)
);

-- 6. TEST ATTEMPTS — Partitioned by month for 1-year retention
CREATE TABLE test_attempts (
    id BIGSERIAL,
    test_execution_id INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    log_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_test_execution
        FOREIGN KEY (test_execution_id)
        REFERENCES test_executions(id) ON DELETE CASCADE
) PARTITION BY RANGE (created_at);

-- Monthly partitions: January 2026 through February 2027
CREATE TABLE test_attempts_2026_01 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE test_attempts_2026_02 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE test_attempts_2026_03 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE test_attempts_2026_04 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE test_attempts_2026_05 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE test_attempts_2026_06 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE test_attempts_2026_07 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE test_attempts_2026_08 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE test_attempts_2026_09 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE test_attempts_2026_10 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE test_attempts_2026_11 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE test_attempts_2026_12 PARTITION OF test_attempts
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
CREATE TABLE test_attempts_2027_01 PARTITION OF test_attempts
    FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');
CREATE TABLE test_attempts_2027_02 PARTITION OF test_attempts
    FOR VALUES FROM ('2027-02-01') TO ('2027-03-01');

CREATE INDEX idx_test_attempts_created_at ON test_attempts (created_at);
CREATE INDEX idx_test_attempts_execution_id ON test_attempts (test_execution_id);

-- 7. ERROR INTELLIGENCE
CREATE TABLE error_patterns (
    fingerprint VARCHAR(64) PRIMARY KEY,
    scrubbed_message TEXT,
    error_class VARCHAR(100),
    resolved_bucket_id INTEGER REFERENCES buckets(id),
    resolved_action VARCHAR(255),
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    global_hit_count INTEGER DEFAULT 1
);

CREATE TABLE triage_signals (
    id SERIAL PRIMARY KEY,
    test_attempt_id BIGINT NOT NULL,
    fingerprint VARCHAR(64) REFERENCES error_patterns(fingerprint) ON DELETE CASCADE,
    bug_id VARCHAR(50),
    UNIQUE(test_attempt_id, fingerprint)
);

CREATE TABLE run_stats_snapshots (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
    bucket_id INTEGER REFERENCES buckets(id),
    feature_count INTEGER DEFAULT 0,
    suite_count INTEGER DEFAULT 0,
    test_count INTEGER DEFAULT 0,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id, bucket_id)
);

-- 8. PERFORMANCE INDEXES
CREATE INDEX idx_error_patterns_bucket ON error_patterns (resolved_bucket_id);
CREATE INDEX idx_test_executions_run ON test_executions (run_id);
CREATE INDEX idx_test_executions_bucket ON test_executions (latest_bucket_id);
CREATE INDEX idx_runs_identifier ON runs (identifier);
