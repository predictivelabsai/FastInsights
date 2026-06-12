"""FastInsights data layer.

One SQLite file holds two things:
  * a synthetic **data warehouse** (a retail sales star schema, tables prefixed
    ``wh_``) — the data analysts explore;
  * the **app metadata** (saved queries, charts, dashboards) — modelled on
    Frappe Insights' Query / Chart / Dashboard doctypes.

Analyst SQL runs through ``run_sql()``, which enforces a single read-only
SELECT so neither the AI text-to-SQL nor the SQL lab can mutate anything.
"""
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.getenv("FASTINSIGHTS_DB") or str(Path(__file__).parent / "fastinsights.sqlite")

CHART_TYPES = ["bar", "line", "pie", "row", "number"]


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def cursor():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def db_exists() -> bool:
    p = Path(DB_PATH)
    return p.exists() and p.stat().st_size > 0


def rows(sql, params=()):
    with cursor() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(sql, params=()):
    with cursor() as conn:
        r = conn.execute(sql, params).fetchone()
        return dict(r) if r else None


def scalar(sql, params=()):
    with cursor() as conn:
        r = conn.execute(sql, params).fetchone()
        return r[0] if r else None


# --- safe read-only SQL runner ---------------------------------------------

class SQLError(Exception):
    pass


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex)\b",
    re.IGNORECASE)


def run_sql(sql: str, limit: int = 500):
    """Execute a single read-only SELECT and return (columns, rows)."""
    s = (sql or "").strip().rstrip(";")
    if not s:
        raise SQLError("Empty query.")
    if ";" in s:
        raise SQLError("Only a single statement is allowed.")
    if not re.match(r"^\s*(select|with)\b", s, re.IGNORECASE):
        raise SQLError("Only SELECT/WITH queries are allowed.")
    if _FORBIDDEN.search(s):
        raise SQLError("Only read-only queries are allowed.")
    if re.search(r"\blimit\b", s, re.IGNORECASE) is None:
        s = f"{s}\nLIMIT {limit}"
    with cursor() as conn:
        try:
            cur = conn.execute(s)
        except sqlite3.Error as e:
            raise SQLError(str(e))
        cols = [d[0] for d in cur.description] if cur.description else []
        data = [list(r) for r in cur.fetchall()]
    return cols, data


def warehouse_schema() -> list[dict]:
    """Return [{table, columns:[(name,type)]}] for the wh_ tables."""
    tables = rows("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'wh_%' ORDER BY name")
    out = []
    for t in tables:
        cols = rows(f"PRAGMA table_info({t['name']})")
        out.append({"table": t["name"], "columns": [(c["name"], c["type"]) for c in cols]})
    return out


def schema_prompt() -> str:
    lines = ["Warehouse tables (SQLite):"]
    for t in warehouse_schema():
        lines.append(f"  {t['table']}(" + ", ".join(f"{n} {ty}" for n, ty in t["columns"]) + ")")
    return "\n".join(lines)


# --- app metadata schema ----------------------------------------------------

APP_SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id            INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT,
    sql           TEXT NOT NULL,
    folder        TEXT
);
CREATE TABLE IF NOT EXISTS charts (
    id            INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    query_id      INTEGER REFERENCES queries(id),
    chart_type    TEXT NOT NULL DEFAULT 'bar',
    x_col         TEXT,
    y_col         TEXT
);
CREATE TABLE IF NOT EXISTS dashboards (
    id            INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT
);
CREATE TABLE IF NOT EXISTS dashboard_charts (
    dashboard_id  INTEGER REFERENCES dashboards(id),
    chart_id      INTEGER REFERENCES charts(id),
    position      INTEGER,
    width         TEXT DEFAULT 'half'   -- 'half' | 'full'
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id            INTEGER PRIMARY KEY,
    thread_id     TEXT NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL,
    created       TEXT NOT NULL
);
"""


def init_app_schema():
    with cursor() as conn:
        conn.executescript(APP_SCHEMA)


# --- convenience reads ------------------------------------------------------

def query(qid: int):
    return one("SELECT * FROM queries WHERE id=?", (qid,))


def chart(cid: int):
    return one("""SELECT ch.*, q.sql, q.title query_title
                  FROM charts ch LEFT JOIN queries q ON q.id=ch.query_id WHERE ch.id=?""", (cid,))


def dashboard_charts(did: int):
    return rows("""SELECT ch.*, q.sql, dc.width, dc.position
                   FROM dashboard_charts dc
                   JOIN charts ch ON ch.id=dc.chart_id
                   LEFT JOIN queries q ON q.id=ch.query_id
                   WHERE dc.dashboard_id=? ORDER BY dc.position""", (did,))


# --- save / delete saved queries (transactional) ----------------------------

def save_query(title: str, sql: str, chart_type: str = "bar", x_col: str = None, y_col: str = None) -> int:
    title = (title or "Untitled query").strip() or "Untitled query"
    if chart_type not in CHART_TYPES:
        chart_type = "bar"
    with cursor() as conn:
        conn.execute("INSERT INTO queries(title,description,sql,folder) VALUES (?,?,?,'Saved')",
                     (title, "Saved from the SQL lab.", sql.strip()))
        qid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO charts(title,query_id,chart_type,x_col,y_col) VALUES (?,?,?,?,?)",
                     (title, qid, chart_type, x_col, y_col))
    return qid


def delete_query(qid: int):
    with cursor() as conn:
        conn.execute("DELETE FROM charts WHERE query_id=?", (qid,))
        conn.execute("DELETE FROM queries WHERE id=?", (qid,))
