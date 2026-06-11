"""Center-pane page renderers for FastInsights."""
from __future__ import annotations

from fasthtml.common import (
    Div, H1, H3, H4, P, Span, A, Table, Thead, Tbody, Tr, Th, Td, Form, Input,
    Textarea, Button, NotStr, Label,
)

import db
from web.layout import kpi_card
from web import charts


def _money(v):
    v = v or 0
    if v >= 1_000_000:
        return f"£{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"£{v/1_000:.0f}k"
    return f"£{v:,.0f}"


def _title(title, sub="", *actions):
    return Div(Div(H1(title), P(sub, cls="sub") if sub else None),
               Div(*actions) if actions else None, cls="page-title")


# ---------- home ------------------------------------------------------------

def home():
    total_rev = db.scalar("SELECT SUM(revenue) FROM wh_orders") or 0
    total_margin = db.scalar("SELECT SUM(revenue-cost) FROM wh_orders") or 0
    orders = db.scalar("SELECT COUNT(*) FROM wh_orders") or 0
    customers = db.scalar("SELECT COUNT(*) FROM wh_customers") or 0
    aov = total_rev / orders if orders else 0

    # render the two flagship charts inline
    chart_blocks = []
    for cid in (1, 2):  # Monthly revenue (line), Revenue by region (bar)
        ch = db.chart(cid)
        if not ch:
            continue
        cols, data = db.run_sql(ch["sql"])
        chart_blocks.append(Div(Div(H3(ch["title"]), cls="card-header"),
                                *charts.plotly(f"home-chart-{cid}", cols, data,
                                               ch["chart_type"], ch["x_col"], ch["y_col"]),
                                cls="card"))

    dashboards = db.rows("SELECT * FROM dashboards")
    dash_links = Div(*[A(Div(H4(d["title"]), P(d["description"], cls="sub")),
                         href=f"/dashboards/{d['id']}", cls="card",
                         style="display:block;color:var(--text);")
                       for d in dashboards], cls="grid-2")

    return (
        _title("Home", "Headline metrics over the synthetic sales warehouse."),
        Div(kpi_card("Total revenue", _money(total_rev), f"{orders:,} orders"),
            kpi_card("Gross margin", _money(total_margin), f"{round(100*total_margin/total_rev) if total_rev else 0}% of revenue"),
            kpi_card("Avg order value", _money(aov)),
            kpi_card("Customers", f"{customers:,}"), cls="kpi-grid"),
        Div(*chart_blocks, cls="grid-2"),
        Div(H3("Dashboards", style="margin:18px 0 10px;font-size:15px;")),
        dash_links,
    )


# ---------- dashboards ------------------------------------------------------

def dashboards_list():
    ds = db.rows("""SELECT d.*, COUNT(dc.chart_id) n FROM dashboards d
                    LEFT JOIN dashboard_charts dc ON dc.dashboard_id=d.id GROUP BY d.id""")
    cards = [A(Div(H3(d["title"]), P(d["description"], cls="sub"),
                   P(f"{d['n']} charts", style="color:var(--text-mute);font-size:12px;margin-top:8px;")),
               href=f"/dashboards/{d['id']}", cls="card", style="display:block;color:var(--text);") for d in ds]
    return _title("Dashboards", f"{len(ds)} dashboards"), Div(*cards, cls="grid-2")


def dashboard_view(did):
    d = db.one("SELECT * FROM dashboards WHERE id=?", (did,))
    if not d:
        return _title("Dashboard not found"), P("No such dashboard.")
    items = db.dashboard_charts(did)
    blocks = []
    for it in items:
        cols, data = db.run_sql(it["sql"])
        blocks.append(Div(Div(Div(H3(it["title"]), cls="card-header"),
                              *charts.plotly(f"dash-{did}-chart-{it['id']}", cols, data,
                                             it["chart_type"], it["x_col"], it["y_col"]), cls="card"),
                          cls=f"dash-item {it['width']}"))
    return (_title(d["title"], d["description"], A("← All dashboards", href="/dashboards", cls="btn")),
            Div(*blocks, cls="dash-grid"))


# ---------- queries & charts ------------------------------------------------

def queries_list():
    qs = db.rows("""SELECT q.*, ch.id chart_id, ch.chart_type FROM queries q
                    LEFT JOIN charts ch ON ch.query_id=q.id ORDER BY q.title""")
    tbl = Table(Thead(Tr(Th("Query"), Th("Description"), Th("Chart"), Th(""))),
                Tbody(*[Tr(Td(A(q["title"], href=f"/queries/{q['id']}")),
                           Td(q["description"] or "—", style="color:var(--text-dim);"),
                           Td(Span(q["chart_type"], cls=f"pill {q['chart_type']}") if q["chart_type"] else "—"),
                           Td(A("Open ↗", href=f"/queries/{q['id']}")))
                        for q in qs]), cls="tbl")
    return _title("Queries & Charts", f"{len(qs)} saved queries"), Div(tbl, cls="card")


def query_view(qid):
    q = db.query(qid)
    if not q:
        return _title("Query not found"), P("No such query.")
    ch = db.one("SELECT * FROM charts WHERE query_id=?", (qid,))
    cols, data = db.run_sql(q["sql"])
    chart_card = None
    if ch:
        chart_card = Div(Div(H3("Chart"), Span(ch["chart_type"], cls=f"pill {ch['chart_type']}"), cls="card-header"),
                         *charts.plotly(f"q-{qid}-chart", cols, data, ch["chart_type"], ch["x_col"], ch["y_col"]),
                         cls="card")
    return (_title(q["title"], q["description"] or "", A("← All queries", href="/queries", cls="btn")),
            chart_card,
            Div(Div(H3("SQL"), cls="card-header"),
                Div(NotStr(f"<pre style='background:#0f172a;color:#e2e8f0;padding:12px;border-radius:8px;overflow-x:auto;font-size:12.5px;'>{q['sql']}</pre>")),
                cls="card"),
            Div(Div(H3("Result"), cls="card-header"), charts.result_table(cols, data), cls="card"))


# ---------- SQL lab + Ask AI ------------------------------------------------

def sql_lab(sql_default=""):
    schema = db.warehouse_schema()
    schema_block = Div(*[Div(Span(t["table"], cls="tn"),
                             Div(", ".join(n for n, _ in t["columns"]), cls="cols"), cls="schema-table")
                         for t in schema], cls="card")
    default = sql_default or "SELECT p.category, ROUND(SUM(o.revenue),0) AS revenue\nFROM wh_orders o JOIN wh_products p ON p.product_id=o.product_id\nGROUP BY p.category ORDER BY revenue DESC"
    return (
        _title("SQL Lab + Ask AI", "Run read-only SQL, or describe what you want and let AI write it."),
        Div(Div(H3("Ask the data in plain English"), cls="card-header"),
            Form(Input(name="question", cls="askbox", placeholder="e.g. monthly revenue for 2025 by channel",
                       autocomplete="off"),
                 Div(Button("Generate SQL & run", cls="btn primary", type="submit"),
                     style="margin-top:8px;"),
                 hx_post="/sql/ask", hx_target="#sql-result", hx_swap="innerHTML",
                 **{"hx-indicator": "#ask-spin"}),
            Span(NotStr("&nbsp;"), id="ask-spin", cls="htmx-indicator"),
            cls="card"),
        Div(Div(H3("SQL"), cls="card-header"),
            Form(Textarea(default, name="sql", cls="sqlbox", spellcheck="false"),
                 Div(Button("Run", cls="btn primary", type="submit"), style="margin-top:8px;"),
                 hx_post="/sql/run", hx_target="#sql-result", hx_swap="innerHTML"),
            cls="card"),
        Div(Div(H3("Schema"), cls="card-header"), schema_block, style="margin-bottom:16px;"),
        Div(id="sql-result"),
    )


def sql_result(sql, ai_note=""):
    try:
        cols, data = db.run_sql(sql)
    except db.SQLError as e:
        return Div(Div(NotStr(f"⚠ {e}"), cls="sql-result-err"), cls="card")
    # auto-pick a chart: first text col = x, first numeric col = y
    x_col = cols[0] if cols else None
    y_col = None
    for i, c in enumerate(cols):
        if i == 0:
            continue
        if data and all(isinstance(charts._num(r[i]), float) for r in data[:10]):
            y_col = c
            break
    ctype = "line" if (x_col and ("month" in x_col.lower() or "date" in x_col.lower())) else "bar"
    blocks = []
    if ai_note:
        blocks.append(Div(NotStr(ai_note), cls="callout",
                          style="background:var(--accent-light);border-left:4px solid var(--accent);color:var(--accent-hover);padding:10px 14px;border-radius:8px;margin-bottom:12px;font-size:13px;"))
    blocks.append(Div(NotStr(f"<pre style='background:#0f172a;color:#e2e8f0;padding:12px;border-radius:8px;overflow-x:auto;font-size:12.5px;'>{sql}</pre>"),
                      cls="card"))
    if y_col:
        blocks.append(Div(Div(H3("Chart"), cls="card-header"),
                          *charts.plotly("ad-hoc-chart", cols, data, ctype, x_col, y_col), cls="card"))
    blocks.append(Div(Div(H3("Result"), cls="card-header"), charts.result_table(cols, data), cls="card"))
    return Div(*blocks)


# ---------- data source -----------------------------------------------------

def sources():
    schema = db.warehouse_schema()
    blocks = []
    for t in schema:
        n = db.scalar(f"SELECT COUNT(*) FROM {t['table']}")
        sample = db.run_sql(f"SELECT * FROM {t['table']} LIMIT 5")
        blocks.append(Div(Div(H3(t["table"]), Span(f"{n:,} rows", cls="pill"), cls="card-header"),
                          charts.result_table(*sample), cls="card"))
    return (_title("Data Source", "Local synthetic warehouse (SQLite) — a retail sales star schema."),
            Div(NotStr("4 tables · one fact (<span class='code'>wh_orders</span>) and three dimensions "
                       "(<span class='code'>wh_customers</span>, <span class='code'>wh_products</span>, "
                       "<span class='code'>wh_regions</span>)."), cls="callout",
                style="background:var(--accent-light);border-left:4px solid var(--accent);color:var(--accent-hover);padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:13px;"),
            *blocks)
