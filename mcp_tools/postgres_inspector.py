"""
PostgreSQL Inspector MCP Tool for Hephaestus
Allows the coding agent to inspect tables, view foreign keys, and query database metadata.
"""
from fastmcp import FastMCP
import os
import psycopg2
from psycopg2.extras import RealDictCursor

mcp = FastMCP("Postgres Inspector")

def get_connection():
    db_url = os.getenv("DATABASE_URL", "postgresql://dbearsong@localhost:5432/hephaestus")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)

@mcp.tool()
def list_tables() -> list:
    """Lists all user tables in the current PostgreSQL database."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)
            rows = cur.fetchall()
            return [r["table_name"] for r in rows]
    finally:
        conn.close()

@mcp.tool()
def describe_table(table_name: str) -> list:
    """Returns column information for a specific table."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, (table_name,))
            return cur.fetchall()
    finally:
        conn.close()

if __name__ == "__main__":
    mcp.run()
