# Internet Insights — Migration Plan

**Version:** 1.0  
**Migration Version Table:** `internet_insights_schema_version`  
**Current Schema Version:** 1

---

## 1. Migration Architecture

### 1.1 Version Table

```sql
CREATE TABLE internet_insights_schema_version (
    version INTEGER PRIMARY KEY
);

-- Initial state (fresh install):
INSERT INTO internet_insights_schema_version (version) VALUES (1);
```

- **Independent** from `history.schema_version` (which is at version 3).
- Single-row table; `version` is the current schema version.
- Migrations are **forward-only** (no down-migrations in normal operation).

### 1.2 Migration Runner

```python
# backend/internet_insights/storage/migrations.py

MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migrate_v1_initial_schema,
    # 2: _migrate_v2_add_column_x,
    # 3: _migrate_v3_rename_table_y,
}

CURRENT_VERSION = max(MIGRATIONS.keys())

def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending migrations. Returns new version."""
    row = conn.execute("SELECT MAX(version) FROM internet_insights_schema_version").fetchone()
    current = row[0] if row and row[0] is not None else 0

    for version in range(current + 1, CURRENT_VERSION + 1):
        if version not in MIGRATIONS:
            raise RuntimeError(f"Missing migration for version {version}")
        logger.info("Applying Internet Insights migration v%d", version)
        MIGRATIONS[version](conn)
        conn.execute("INSERT OR REPLACE INTO internet_insights_schema_version (version) VALUES (?)", (version,))
        conn.commit()
        logger.info("Migration v%d complete", version)

    return CURRENT_VERSION
```

### 1.3 Migration Rules

1. **Idempotent** — Safe to run multiple times (use `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`).
2. **Transactional** — Each migration runs in a single transaction (implicit via `isolation_level=None` + explicit `commit`).
3. **No data loss** — Migrations only add tables/columns/indexes; never drop data.
4. **Backward compatible** — New columns default to `NULL` or sensible defaults.
5. **Ordered** — Migrations apply sequentially from `current + 1` to `CURRENT_VERSION`.

---

## 2. Migration v1 — Initial Schema (Current)

**Applied on first run** when `internet_insights_schema_version` is empty or version 0.

Creates all 9 tables + indexes defined in `INTERNET_INSIGHTS_DATA_MODEL.md`:

1. `internet_quality_samples`
2. `internet_interface_samples`
3. `internet_tcp_stats_samples`
4. `internet_dns_probe_samples`
5. `internet_diagnostic_sessions`
6. `internet_diagnostic_results`
7. `internet_incidents`
8. `internet_incident_evidence`
9. `internet_insights_schema_version` (with version=1)

```python
def _migrate_v1_initial_schema(conn: sqlite3.Connection) -> None:
    # All CREATE TABLE and CREATE INDEX statements from DATA_MODEL.md
    # Executed as a single executescript() for atomicity
    conn.executescript(V1_SCHEMA_SQL)
    conn.execute("INSERT INTO internet_insights_schema_version (version) VALUES (1)")
```

---

## 3. Future Migration Examples

### 3.1 v2 — Add `interface_alias` Column

```python
def _migrate_v2_add_interface_alias(conn: sqlite3.Connection) -> None:
    conn.execute("""
        ALTER TABLE internet_interface_samples
        ADD COLUMN interface_alias TEXT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_interface_alias ON internet_interface_samples (interface_alias)")
```

### 3.2 v3 — Add Downsampled Hourly Aggregates Table

```python
def _migrate_v3_add_hourly_aggregates(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS internet_quality_hourly (
            hour_start INTEGER NOT NULL,      -- Unix timestamp truncated to hour
            target_id TEXT NOT NULL,
            probe_type TEXT NOT NULL,
            sample_count INTEGER NOT NULL,
            min_rtt_ms REAL,
            median_rtt_ms REAL,
            p95_rtt_ms REAL,
            max_rtt_ms REAL,
            timeout_count INTEGER DEFAULT 0,
            loss_pct REAL,
            PRIMARY KEY (hour_start, target_id, probe_type)
        );
        CREATE INDEX IF NOT EXISTS idx_quality_hourly_target ON internet_quality_hourly (target_id, hour_start);
    """)
```

### 3.3 v4 — Add `incident_correlation_id` for Multi-Incident Correlation

```python
def _migrate_v4_add_correlation_id(conn: sqlite3.Connection) -> None:
    conn.execute("""
        ALTER TABLE internet_incidents
        ADD COLUMN correlation_id TEXT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_incident_correlation ON internet_incidents (correlation_id)")
```

---

## 4. Upgrade Path

### 4.1 Fresh Install (v0.7.0+)

1. Application starts → `InternetInsightsDB._get_conn()` opens connection.
2. `run_migrations(conn)` called during initialization.
3. Version table empty → treated as version 0.
4. Migration v1 applied → all tables created, version set to 1.
5. Collectors start → begin writing samples.

### 4.2 Upgrade from v0.7.0 to v0.7.1 (Schema v1 → v2)

1. User updates application.
2. Application starts → `run_migrations(conn)` called.
4. Current version = 1, target = 2.
5. Migration v2 applied → `interface_alias` column added.
6. Version updated to 2.
7. Collectors continue; new column populated on next writes.

### 4.3 Skip Version (v0.7.0 → v0.8.0, Schema v1 → v3)

1. User jumps versions (e.g., skipped v0.7.1).
2. `run_migrations` applies v2, then v3 sequentially.
3. Each migration commits independently.
4. Final version = 3.

---

## 5. Rollback Strategy

### 5.1 No Automatic Rollback

- Migrations are **forward-only** in production.
- Down-migrations (dropping columns/tables) are **not provided** — risk of data loss.
- If a migration fails, the application logs error and **does not start** Internet Insights collectors.

### 5.2 Manual Rollback Procedure (Emergency Only)

If a migration introduces a critical bug:

1. **Stop the application** immediately.
2. **Backup** `backend/.cache/history.db` (copy file).
3. **Manual SQLite commands** to revert:
   ```sql
   -- Example: revert v2 (drop added column)
   -- SQLite doesn't support DROP COLUMN directly before 3.35.0
   -- Use table rebuild:
   CREATE TABLE internet_interface_samples_old AS
     SELECT id, ts, interface_id, bytes_sent, bytes_recv, send_bps, recv_bps,
            packets_sent, packets_recv, errors_in, errors_out, discards_in, discards_out, link_status
     FROM internet_interface_samples;
   DROP TABLE internet_interface_samples;
   ALTER TABLE internet_interface_samples_old RENAME TO internet_interface_samples;
   -- Recreate indexes
   CREATE INDEX idx_interface_id_ts ON internet_interface_samples (interface_id, ts);
   CREATE INDEX idx_interface_ts ON internet_interface_samples (ts);
   ```
4. **Downgrade version table:**
   ```sql
   UPDATE internet_insights_schema_version SET version = 1;
   ```
5. **Restart application** — collectors will use v1 schema.

### 5.3 Rollback Testing

- Every migration must have a documented rollback procedure in its docstring.
- Integration tests include: apply v1→v2→v3, then manual rollback v3→v2→v1, verify data integrity.

---

## 6. Coexistence with Existing History Module

### 6.1 Separate Version Namespaces

| Module | Version Table | Current Version |
|--------|---------------|-----------------|
| `history.py` | `schema_version` | 3 |
| Internet Insights | `internet_insights_schema_version` | 1 |

- **No coupling** — each module manages its own migrations.
- `history.py` migrations never touch Internet Insights tables.
- Internet Insights migrations never touch `samples` or `schema_version`.

### 6.2 Shared Database File

Both modules use `backend/.cache/history.db` (SQLite WAL).

- WAL mode allows **concurrent readers + single writer** per connection.
- Internet Insights uses **separate connection pool** (`InternetInsightsDB`).
- `history.py` uses its own `_conn` and `_lock`.
- No cross-module locking — SQLite WAL handles concurrency.

### 6.3 Migration Ordering

On application startup:

1. `history.py` initializes → runs its migrations (v1→v2→v3).
2. Internet Insights initializes → runs its migrations (v1→...).
3. Order **does not matter** — independent tables.

---

## 7. Testing Requirements

### 7.1 Unit Tests

- `test_migrations.py`: Apply each migration in isolation, verify schema.
- `test_migration_sequence.py`: Apply v1→v2→v3 sequentially, verify final schema.
- `test_rollback_procedures.py`: Document and test manual rollback for each migration.

### 7.2 Integration Tests

- **Fresh DB**: Start app on empty `history.db` → verify all tables created, version=1.
- **Upgrade DB**: Copy v0.6.3 `history.db` (with `schema_version`=3, no Internet Insights tables) → start v0.7.0 app → verify Internet Insights tables created, `schema_version` unchanged.
- **Concurrent Access**: Run `history.record_sample()` and Internet Insights collectors simultaneously → verify no lock contention, no data corruption.

### 7.3 Migration Performance

- v1 (initial) must complete in < 500 ms on reference hardware.
- Subsequent migrations (ALTER TABLE) must complete in < 100 ms.
- No migration may block startup for > 2 seconds.

---

## 8. Deployment Checklist

| Step | Description |
|------|-------------|
| ☐ | Migration runner integrated in `InternetInsightsDB.__init__` |
| ☐ | v1 schema SQL matches `INTERNET_INSIGHTS_DATA_MODEL.md` exactly |
| ☐ | Version table created with correct initial value |
| ☐ | All migrations are idempotent (safe to re-run) |
| ☐ | Rollback procedure documented for each migration |
| ☐ | Integration test: fresh install works |
| ☐ | Integration test: upgrade from v0.6.3 DB works |
| ☐ | `history.py` schema_version unaffected |
| ☐ | No data loss in any migration path |