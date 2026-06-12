"""FastInsights — an open-source BI tool built with FastHTML.

A server-side, HTMX-driven port of the core of Frappe Insights: a synthetic
data warehouse, saved queries that render Plotly charts, dashboards, a SQL lab,
and an AI text-to-SQL assistant — all read-only over synthetic data.

Run:
    python web_app.py            # http://localhost:5008

Login: admin@fastinsights.example / FastInsights2026$  (override via .env)
"""
from __future__ import annotations

import os
import json
import secrets
import uuid
import logging

from dotenv import load_dotenv
load_dotenv()

from fasthtml.common import (
    fast_app, serve, Div, H1, P, A, Form, Input, Button, NotStr,
    RedirectResponse, Script, Style, Link, Title,
)
from starlette.responses import StreamingResponse, Response

import db
from web.layout import page, LAYOUT_CSS
from web import views, ai

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("fastinsights")

VALID_EMAIL = os.getenv("FASTINSIGHTS_ADMIN_EMAIL", "admin@fastinsights.example")
VALID_PASSWORD = os.getenv("FASTINSIGHTS_ADMIN_PASSWORD", "FastInsights2026$")
ENV_LABEL = os.getenv("FASTINSIGHTS_ENV_LABEL", "FastInsights")
SECRET = os.getenv("FASTINSIGHTS_SECRET", secrets.token_hex(32))
PORT = int(os.getenv("FASTINSIGHTS_PORT", "5008"))

app, rt = fast_app(live=False, pico=False, secret_key=SECRET, hdrs=[Style(LAYOUT_CSS)])


def _user(session):
    return session.get("user")


def _thread(session):
    if "thread" not in session:
        session["thread"] = uuid.uuid4().hex
    return session["thread"]


def _guard(session, active, builder):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    content = builder() if callable(builder) else builder
    if not isinstance(content, tuple):
        content = (content,)
    return page(active, ENV_LABEL, _user(session), _thread(session), *content)


def _login_card(error="", email=""):
    return Title("FastInsights — Sign in"), Style(LAYOUT_CSS), Div(
        Form(H1("FastInsights"), P("Sign in to your BI workspace"),
             Input(name="email", type="email", placeholder="Email", value=email, required=True),
             Input(name="password", type="password", placeholder="Password", required=True),
             P(error, cls="error") if error else None,
             Button("Sign in", cls="btn primary", type="submit"),
             P(NotStr("Demo: <code>admin@fastinsights.example</code> / <code>FastInsights2026$</code>"), cls="hint"),
             method="post", action="/login", cls="login-card"), cls="login-wrap")


@rt("/login")
def get(session):
    if _user(session):
        return RedirectResponse("/", status_code=303)
    return _login_card()


@rt("/login")
def post(session, email: str = "", password: str = ""):
    if email.strip().lower() == VALID_EMAIL.lower() and password == VALID_PASSWORD:
        session["user"] = email.strip().lower()
        return RedirectResponse("/", status_code=303)
    return _login_card("Invalid email or password.", email)


@rt("/logout")
def get(session):
    session.pop("user", None)
    return RedirectResponse("/login", status_code=303)


@rt("/")
def get(session):
    return _guard(session, "home", views.home)


@rt("/dashboards")
def get(session):
    return _guard(session, "dashboards", views.dashboards_list)


@rt("/dashboards/{did}")
def get(session, did: int):
    return _guard(session, "dashboards", lambda: views.dashboard_view(did))


@rt("/queries")
def get(session):
    return _guard(session, "queries", views.queries_list)


@rt("/queries/save")
def post(session, title: str = "", sql: str = "", chart_type: str = "bar", x_col: str = "", y_col: str = ""):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    try:
        db.run_sql(sql)  # validate before saving
    except db.SQLError:
        return RedirectResponse("/sql", status_code=303)
    qid = db.save_query(title, sql, chart_type, x_col or None, y_col or None)
    return RedirectResponse(f"/queries/{qid}", status_code=303)


@rt("/queries/{qid}/delete")
def post(session, qid: int):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    db.delete_query(qid)
    return RedirectResponse("/queries", status_code=303)


@rt("/queries/{qid}")
def get(session, qid: int):
    return _guard(session, "queries", lambda: views.query_view(qid))


@rt("/sql")
def get(session):
    return _guard(session, "sqllab", views.sql_lab)


@rt("/sql/run")
def post(session, sql: str = ""):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    return views.sql_result(sql)


@rt("/sql/ask")
def post(session, question: str = ""):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    question = (question or "").strip()
    if not question:
        return Div(P("Type a question first.", style="color:var(--text-mute);"), cls="card")
    try:
        sql, note = ai.text_to_sql(question)
    except Exception as e:  # noqa: BLE001
        return Div(Div(NotStr(f"⚠ {e}"), cls="sql-result-err"), cls="card")
    return views.sql_result(sql, ai_note=note)


@rt("/sources")
def get(session):
    return _guard(session, "sources", views.sources)


@rt("/ai")
def get(session):
    body = (views._title("AI Assistant", "Chat lives in the right rail. For SQL generation, use the SQL Lab."),
            Div(NotStr(
                "<div class='card'><h3>What you can ask</h3><ul style='line-height:1.8;'>"
                "<li>“What's our total revenue and margin?”</li>"
                "<li>“Which region and category perform best?”</li>"
                "<li>“How is revenue trending?”</li></ul>"
                "<p style='color:var(--text-mute)'>Slash-commands (no API key): "
                "<code>/metrics</code> <code>/tables</code> <code>/top region|category|customer</code></p>"
                "<p>Want a custom query? The <a href='/sql'>SQL Lab</a> turns a plain-English question "
                "into a read-only SQL query, runs it, and charts the result.</p></div>")))
    return _guard(session, "ai", body)


@rt("/guide")
def get(session):
    body = (views._title("User Guide", "How to drive FastInsights"), Div(NotStr("""
<div class='card'><h3>Home</h3><p>Headline KPIs plus two flagship charts and links to your dashboards.</p></div>
<div class='card'><h3>Dashboards</h3><p>Curated boards of charts in a responsive grid.</p></div>
<div class='card'><h3>Queries & Charts</h3><p>Saved SQL queries, each bound to a chart type. Open one to see the
chart, the SQL, and the full result table.</p></div>
<div class='card'><h3>SQL Lab + Ask AI</h3><p>Run read-only SQL against the warehouse, or describe what you want and
let the AI generate the SQL, run it, and chart it. The schema is shown alongside.</p></div>
<div class='card'><h3>Data Source</h3><p>Browse the synthetic warehouse tables with row counts and samples.</p></div>
""")))
    return _guard(session, "guide", body)


@rt("/chat/new")
def get(session):
    session["thread"] = uuid.uuid4().hex
    return P("Ask about your metrics — or use /tables /metrics /help.", cls="chat-empty-hint")


@rt("/chat/stream")
async def post(session, message: str = "", thread_id: str = ""):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    message = (message or "").strip()
    if not message:
        return Response("No message", status_code=400)
    tid = thread_id or _thread(session)

    async def gen():
        with db.cursor() as conn:
            conn.execute("INSERT INTO chat_messages(thread_id,role,content,created) VALUES(?,?,?,datetime('now'))",
                         (tid, "user", message))
        full = []
        async for chunk in ai.stream_chat(message):
            if chunk.startswith("data: "):
                try:
                    tok = json.loads(chunk[6:]).get("token")
                    if tok:
                        full.append(tok)
                except Exception:
                    pass
            yield chunk
        with db.cursor() as conn:
            conn.execute("INSERT INTO chat_messages(thread_id,role,content,created) VALUES(?,?,?,datetime('now'))",
                         (tid, "assistant", "".join(full)))

    return StreamingResponse(gen(), media_type="text/event-stream")


def _ensure_db():
    if not db.db_exists():
        logger.info("No database found — seeding synthetic warehouse…")
        import seed
        seed.build()


_ensure_db()

if __name__ == "__main__":
    logger.info("FastInsights on http://localhost:%s  (login %s)", PORT, VALID_EMAIL)
    serve(port=PORT, reload=os.getenv("FASTINSIGHTS_RELOAD", "0") == "1")
