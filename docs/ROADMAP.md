# FastInsights Roadmap — Frappe Insights feature comparison

FastInsights ports the **core** of [Frappe Insights](https://github.com/frappe/insights)
(~38 doctypes) to a FastHTML demonstrator.

## Implemented ✅

| Capability | Upstream doctype(s) | FastInsights |
|---|---|---|
| Data source | `Insights Data Source v3` | local synthetic SQLite warehouse (`wh_*`) |
| Tables browser | `Insights Table v3` | `/sources` with schema + samples |
| Queries | `Insights Query v3` | `queries` (saved SQL) + SQL lab |
| Charts | `Insights Chart v3` | `charts` + Plotly (bar/line/pie/row) |
| Dashboards | `Insights Dashboard v3`/`Item` | `dashboards` + responsive grid |
| Read-only execution | query engine | `db.run_sql()` guard (single SELECT only) |
| **AI text-to-SQL** | *(not upstream)* | natural language → SQL → chart |
| Metric chat | *(not upstream)* | grounded multi-provider assistant |

## Near-term roadmap 🔜

1. **Save ad-hoc queries** — let the SQL lab / AI result be saved as a new
   `query` + `chart` (currently the 7 saved queries are seeded).
2. **Query builder** — `is_builder_query` (no-SQL visual builder: pick table,
   columns, filters, group-by) for non-technical users.
3. **Dashboard editor** — add/remove/reorder charts, resize tiles
   (`Insights Dashboard Item` layout), and dashboard-level filters.
4. **Workbooks & folders** — `Insights Workbook`, `Folder` (organise queries
   and charts into projects).
5. **Variables / parameters** — `Insights Query Variable` (parameterised
   queries, e.g. a date-range or region selector).
6. **Alerts** — `Insights Alert` (threshold alerts on a metric).

## Later / out-of-scope 🗓️

- **Live external connections** — `Insights Data Source v3` connects to MySQL,
  Postgres, BigQuery, the site DB, etc. FastInsights uses a bundled SQLite
  warehouse; a read-only external-DB connector is the natural next step.
- **Query transforms / pivot / joins UI** — `Insights Query Transform`,
  multi-query references (`Insights Query Reference`).
- **Notebooks** — `Insights Notebook`/`Page` (Python/markdown analysis notebooks).
- **Team permissions & sharing** — `Insights Team`, `Resource Permission`,
  public share links.
- **Stored-procedure execution**, caching, scheduled refresh.

## Design notes

The headline is **AI text-to-SQL with a hard read-only guard**: `db.run_sql()`
rejects anything that isn't a single `SELECT`/`WITH`, blocks DML/DDL keywords,
and auto-applies a `LIMIT`. This lets the LLM (or a curious analyst) write
arbitrary queries safely against the warehouse. Charts are server-rendered
Plotly specs (`web/charts.py`); the dashboard composer that lets users assemble
those into boards is the most valuable next feature.
