"""
ARA-1 Database Schema Diagnostic Script
Checks what actually exists in PostgreSQL vs what the models expect.
"""
import asyncio
import asyncpg

DB_URL = "postgresql://ara1_user:ara1_secure_password_change_me@localhost:5432/ara1"

EXPECTED_COLUMNS = {
    "research_sessions": [
        "id", "query", "company_ticker", "company_name", "status",
        "plan", "subtasks", "total_tool_calls", "total_tokens_used",
        "error_message", "duration_seconds", "created_at", "started_at", "completed_at"
    ],
    "agent_traces": [
        "id", "session_id", "agent_name", "iteration", "status",
        "input_data", "output_data", "reasoning", "errors",
        "tokens_used", "started_at", "completed_at", "duration_ms"
    ],
    "tool_calls": [
        "id", "session_id", "agent_trace_id", "tool_name",
        "input_args", "output_data", "success", "error_message",
        "duration_ms", "tokens_used", "called_at"
    ],
    "episodic_memories": [
        "id", "session_id", "query", "company_ticker",
        "reasoning_path", "tools_used", "agents_executed",
        "errors_encountered", "conflicts_resolved", "final_report_id",
        "evaluation_score", "success", "created_at", "qdrant_id"
    ],
}

async def main():
    print("=" * 60)
    print("ARA-1 PostgreSQL Schema Diagnostic")
    print("=" * 60)

    try:
        conn = await asyncpg.connect(DB_URL)
        print("[OK] Connected to PostgreSQL\n")
    except Exception as e:
        print(f"[FAIL] Cannot connect to PostgreSQL: {e}")
        return

    # Check alembic_version
    try:
        rows = await conn.fetch("SELECT version_num FROM alembic_version")
        if rows:
            print(f"[OK] Alembic version applied: {[r['version_num'] for r in rows]}")
        else:
            print("[WARN] alembic_version table exists but has NO rows — migrations were NOT applied!")
    except Exception as e:
        print(f"[FAIL] alembic_version table does not exist: {e}")
        print("  -> Migrations have NEVER been run!")

    print()

    # List all tables
    tables_raw = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    existing_tables = {r["tablename"] for r in tables_raw}
    print(f"Existing tables: {sorted(existing_tables)}\n")

    # Check each expected table
    missing_tables = []
    for table, expected_cols in EXPECTED_COLUMNS.items():
        if table not in existing_tables:
            print(f"[MISSING TABLE] {table}")
            missing_tables.append(table)
            continue

        # Get actual columns
        actual_cols_raw = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position",
            table
        )
        actual_col_names = {r["column_name"] for r in actual_cols_raw}
        actual_col_info = {r["column_name"]: r["data_type"] for r in actual_cols_raw}

        missing_cols = [c for c in expected_cols if c not in actual_col_names]
        extra_cols = [c for c in actual_col_names if c not in expected_cols]

        if missing_cols:
            print(f"[MISMATCH] {table} — MISSING columns: {missing_cols}")
        else:
            print(f"[OK] {table} — all expected columns present")

        if extra_cols:
            print(f"  Extra cols in DB (not in model): {extra_cols}")

        print(f"  Actual columns: {sorted(actual_col_names)}")
        print()

    if missing_tables:
        print("\n[ACTION NEEDED] Some tables are missing — run: alembic upgrade head")

    await conn.close()
    print("\nDiagnostic complete.")

if __name__ == "__main__":
    asyncio.run(main())
