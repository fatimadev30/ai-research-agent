"""AI Web Research Agent — Streamlit Application

A research workspace that accepts natural-language instructions, searches the web
via TinyFish, extracts structured data, and exports to Excel, CSV, Word, PDF,
and Google Sheets.
"""

from __future__ import annotations

import os
import sys
import time

import streamlit as st

# Ensure project root is on the path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_settings  # noqa: E402
from services.export_service import export_records  # noqa: E402
from services.repositories import (  # noqa: E402
    create_export_job,
    create_job,
    delete_job,
    delete_record,
    get_job,
    get_job_records,
    get_job_search_queries,
    get_job_source_pages,
    get_job_records,
    list_exports,
    list_jobs,
    update_record_fields,
)
from services.research_planner import parse_prompt  # noqa: E402
from services.tinyfish_client import TinyFishClient  # noqa: E402
from workers.research_worker import cancel_job, get_job_status, is_job_running, start_job  # noqa: E402

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Web Research Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polish.
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .main-header h1 {
        color: #f8fafc !important;
        margin: 0;
        font-size: 1.8rem;
    }
    .main-header p {
        color: #94a3b8 !important;
        margin: 0.3rem 0 0 0;
        font-size: 0.9rem;
    }
    .metric-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        text-align: center;
    }
    .metric-card .value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #1e293b;
    }
    .metric-card .label {
        font-size: 0.75rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.8rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-running { background: #dbeafe; color: #1d4ed8; }
    .status-completed { background: #dcfce7; color: #16a34a; }
    .status-failed { background: #fee2e2; color: #dc2626; }
    .status-cancelled { background: #fef3c7; color: #d97706; }
    .status-draft { background: #f1f5f9; color: #64748b; }
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

def init_state():
    defaults = {
        "current_job_id": None,
        "plan": None,
        "editing_prompt": "",
        "submitted": False,
        "last_refresh": 0.0,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_state()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown("""
<div class="main-header">
    <h1>AI Web Research Agent</h1>
    <p>Search the web, extract structured data, and export to Excel, CSV, Word, PDF, or Google Sheets.</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Navigation")
    page = st.radio(
        "Go to",
        ["New Research", "Job History", "Results & Export", "Source Inspector", "Export History", "Connection Status"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Powered by TinyFish + Supabase")


# ---------------------------------------------------------------------------
# Connection status check
# ---------------------------------------------------------------------------

settings = get_settings()
tinyfish = TinyFishClient(settings=settings)


def render_connection_status():
    st.subheader("Connection Status")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**TinyFish (Web Search)**")
        if settings.has_tinyfish:
            st.success("API key configured")
        else:
            st.error("Not configured")
            st.caption("Set `TINYFISH_API_KEY` in your .env file or Streamlit secrets.")

    with col2:
        st.markdown("**Database (Supabase)**")
        if settings.has_supabase:
            st.success("Connected")
        else:
            st.error("Not configured")
            st.caption("Set `SUPABASE_URL` and `SUPABASE_ANON_KEY`.")

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("**Google Sheets**")
        if settings.has_google:
            st.success("Configured")
        else:
            st.warning("Optional — not configured")
            st.caption("Set `GOOGLE_CLIENT_SECRETS_PATH` to enable.")

    with col4:
        st.markdown("**TinyFish Smoke Test**")
        if settings.has_tinyfish:
            if st.button("Run Smoke Test", key="smoke"):
                with st.spinner("Testing TinyFish connection..."):
                    result = tinyfish.smoke_test()
                if result["ok"]:
                    st.success(f"Search: {result['search_results']} results. Fetch: {result['content_length']} chars from {result['fetched_url'][:60]}...")
                else:
                    st.error(f"Failed: {result['error']}")
        else:
            st.info("Configure TinyFish key first.")


# ---------------------------------------------------------------------------
# New Research page
# ---------------------------------------------------------------------------

def render_new_research():
    st.header("New Research")

    # -- Prompt input --
    prompt = st.text_area(
        "Describe your research task",
        value=st.session_state.editing_prompt,
        height=120,
        placeholder="e.g., Find 50 AI companies in Pakistan. Collect company name, website, city, services, contact email, LinkedIn URL, and source URL.",
        help="Write in plain English. The planner will extract the target count, fields, and geography automatically.",
    )

    col_settings1, col_settings2, col_settings3 = st.columns(3)
    with col_settings1:
        target_count = st.number_input("Target records", min_value=1, max_value=500, value=50, help="Maximum records to extract (capped at 500).")
    with col_settings2:
        batch_size = st.number_input("Batch size", min_value=1, max_value=50, value=20)
    with col_settings3:
        concurrency = st.number_input("Concurrency", min_value=1, max_value=10, value=3, help="Pages to fetch simultaneously.")

    export_format = st.selectbox("Export format", ["xlsx", "csv", "docx", "pdf", "google_sheets"], help="Default export format. You can change this later.")

    col_btn1, col_btn2, _ = st.columns([1, 1, 3])
    with col_btn1:
        if st.button("Generate Plan", type="primary", disabled=not prompt.strip()):
            st.session_state.editing_prompt = prompt
            try:
                plan = parse_prompt(
                    prompt,
                    target_count=target_count,
                    batch_size=batch_size,
                    max_concurrency=concurrency,
                    export_format=export_format,
                )
                st.session_state.plan = plan
            except ValueError as exc:
                st.error(f"Could not parse prompt: {exc}")
            st.rerun()

    with col_btn2:
        if st.button("Clear", disabled=not prompt.strip()):
            st.session_state.editing_prompt = ""
            st.session_state.plan = None
            st.rerun()

    # -- Plan preview / editor --
    plan = st.session_state.plan
    if plan is None:
        st.info("Enter a research task above and click **Generate Plan** to see the structured plan.")
        _show_example_prompts()
        return

    st.divider()
    st.subheader("Research Plan")
    st.markdown("Review and adjust the plan before starting the job.")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.markdown("**Objective**")
        plan.objective = st.text_area("Objective", value=plan.objective, height=60, label_visibility="collapsed")

        st.markdown("**Geography**")
        plan.geography = st.text_input("Geography", value=plan.geography, label_visibility="collapsed")

        st.markdown("**Search Queries** (one per line)")
        queries_text = st.text_area(
            "Search Queries",
            value="\n".join(plan.search_queries),
            height=100,
            label_visibility="collapsed",
        )
        plan.search_queries = [q.strip() for q in queries_text.split("\n") if q.strip()]

    with col_p2:
        st.markdown("**Extraction Fields** (one per line)")
        fields_text = st.text_area(
            "Fields",
            value="\n".join(plan.fields),
            height=100,
            label_visibility="collapsed",
        )
        plan.fields = [f.strip() for f in fields_text.split("\n") if f.strip()]

        st.markdown("**Dedup Keys** (comma-separated)")
        dedup_text = st.text_input("Dedup Keys", value=", ".join(plan.dedup_keys), label_visibility="collapsed")
        plan.dedup_keys = [k.strip() for k in dedup_text.split(",") if k.strip()]

    col_start, col_cancel, _ = st.columns([1, 1, 3])
    with col_start:
        if st.button("Start Research", type="primary"):
            if not settings.has_tinyfish:
                st.error("Cannot start: TinyFish API key is not configured. See Connection Status in the sidebar.")
                return
            if not settings.has_supabase:
                st.error("Cannot start: Supabase is not configured.")
                return

            job_row = create_job(plan.to_dict())
            job_id = job_row.get("id")
            st.session_state.current_job_id = job_id
            start_job(job_id, plan)
            st.success(f"Research job started! Job ID: {job_id[:8]}...")
            time.sleep(1)
            st.rerun()

    with col_cancel:
        if st.button("Discard Plan"):
            st.session_state.plan = None
            st.rerun()


def _show_example_prompts():
    with st.expander("Example prompts"):
        st.markdown("""
**Companies:**
> Find 100 AI companies in Pakistan. Collect company name, official website, city, services, contact email, LinkedIn URL, and source URL.

**Academics:**
> Find 50 professors at Chinese universities working on medical imaging and computer vision. Collect name, university, department, research interests, official profile, email, and publications.

**General:**
> Find 30 coffee roasteries in Berlin. Collect name, website, address, phone, and description.
        """)


# ---------------------------------------------------------------------------
# Job History page
# ---------------------------------------------------------------------------

def render_job_history():
    st.header("Research History")

    try:
        jobs = list_jobs(limit=100)
    except Exception as exc:
        st.error(f"Could not load jobs: {exc}")
        return

    if not jobs:
        st.info("No research jobs yet. Create one from **New Research**.")
        return

    for job in jobs:
        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
            with col1:
                status = job.get("status", "draft")
                badge_class = f"status-{status}"
                st.markdown(
                    f"**{job.get('name') or job.get('objective', 'Untitled')[:60] or 'Untitled job'}** "
                    f'<span class="status-badge {badge_class}">{status}</span>',
                    unsafe_allow_html=True,
                )
                st.caption(f"{job.get('prompt', '')[:100]}...")

            with col2:
                st.metric("Records", job.get("records_validated", 0))
            with col3:
                st.metric("Queries", job.get("queries_executed", 0))
            with col4:
                st.metric("Pages", job.get("pages_fetched", 0))
            with col5:
                if st.button("Open", key=f"open_{job['id']}"):
                    st.session_state.current_job_id = job["id"]
                    st.rerun()

                if st.button("Delete", key=f"del_{job['id']}"):
                    delete_job(job["id"])
                    if st.session_state.current_job_id == job["id"]:
                        st.session_state.current_job_id = None
                    st.rerun()


# ---------------------------------------------------------------------------
# Results & Export page
# ---------------------------------------------------------------------------

def render_results():
    st.header("Results & Export")

    job_id = st.session_state.current_job_id
    if not job_id:
        st.info("Select a job from **Research History** or start a new one.")
        return

    job = get_job(job_id)
    if not job:
        st.error("Job not found.")
        st.session_state.current_job_id = None
        st.rerun()
        return

    # -- Job status bar --
    _render_job_status_bar(job)

    # -- Live progress if running --
    if is_job_running(job_id):
        _render_live_progress(job_id)
        auto_refresh = st.checkbox("Auto-refresh", value=True)
        if auto_refresh:
            time.sleep(3)
            st.rerun()

    # -- Results table --
    try:
        records = get_job_records(job_id)
    except Exception as exc:
        st.error(f"Could not load records: {exc}")
        return

    if not records:
        st.info("No records yet. The job may still be running or found no results.")
        return

    # Build display rows from JSONB fields.
    display_rows = []
    for rec in records:
        row = dict(rec.get("fields", {}))
        row["_id"] = rec.get("id")
        row["_validation_status"] = rec.get("validation_status")
        display_rows.append(row)

    # Determine columns.
    all_columns: list[str] = []
    for row in display_rows:
        for key in row:
            if not key.startswith("_") and key not in all_columns:
                all_columns.append(key)

    st.subheader(f"Extracted Records ({len(display_rows)})")

    # -- Filters --
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        search_term = st.text_input("Search within results", placeholder="Filter by keyword...")
    with col_f2:
        status_filter = st.selectbox("Filter by status", ["All", "validated", "failed", "pending"])

    filtered_rows = display_rows
    if search_term:
        filtered_rows = [
            r for r in filtered_rows
            if any(search_term.lower() in str(v).lower() for v in r.values() if v)
        ]
    if status_filter != "All":
        filtered_rows = [r for r in filtered_rows if r.get("_validation_status") == status_filter]

    st.caption(f"Showing {len(filtered_rows)} of {len(display_rows)} records.")

    # -- Editable table --
    _render_editable_table(filtered_rows, all_columns, job_id)

    # -- Export section --
    st.divider()
    _render_export_section(job, display_rows, all_columns)


def _render_job_status_bar(job):
    status = job.get("status", "draft")
    badge_class = f"status-{status}"
    st.markdown(
        f"### {job.get('objective', 'Untitled')[:80]} "
        f'<span class="status-badge {badge_class}">{status}</span>',
        unsafe_allow_html=True,
    )
    if job.get("error_message"):
        st.error(f"Last error: {job['error_message']}")

    cols = st.columns(7)
    metrics = [
        ("Queries", job.get("queries_executed", 0)),
        ("URLs Found", job.get("urls_discovered", 0)),
        ("Pages Fetched", job.get("pages_fetched", 0)),
        ("Extracted", job.get("records_extracted", 0)),
        ("Validated", job.get("records_validated", 0)),
        ("Duplicates", job.get("duplicates_removed", 0)),
        ("Failed", job.get("failed_records", 0)),
    ]
    for col, (label, value) in zip(cols, metrics):
        col.markdown(f"""
        <div class="metric-card">
            <div class="value">{value}</div>
            <div class="label">{label}</div>
        </div>
        """, unsafe_allow_html=True)


def _render_live_progress(job_id):
    target = 0
    job = get_job(job_id)
    if job:
        target = job.get("target_count", 1)
    validated = job.get("records_validated", 0) if job else 0
    progress = min(validated / max(target, 1), 1.0)
    st.progress(progress, text=f"{validated} / {target} records extracted")

    if job:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Cancel Job"):
                cancel_job(job_id)
                st.warning("Cancellation signal sent.")
                time.sleep(1)
                st.rerun()
        with col2:
            status_info = get_job_status(job_id)
            if status_info["running"]:
                st.info("Job is running in background...")


def _render_editable_table(rows, columns, job_id):
    if not rows:
        st.info("No records match the current filters.")
        return

    # Pagination.
    page_size = st.selectbox("Rows per page", [10, 25, 50, 100], index=1, key="page_size")
    total_pages = max(1, (len(rows) + page_size - 1) // page_size)
    page_num = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key="page_num")
    start = (page_num - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]

    # Display as a data table with column selection.
    display_cols = st.multiselect(
        "Columns to display",
        options=columns,
        default=columns[:6] if len(columns) > 6 else columns,
        key="display_cols",
    )

    # Build display DataFrame.
    import pandas as pd

    display_data = []
    for row in page_rows:
        display_data.append({c: row.get(c, "") for c in display_cols})
    if display_data:
        df = pd.DataFrame(display_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # -- Inline editing --
    with st.expander("Edit a record"):
        editable_ids = [r["_id"] for r in page_rows if r.get("_id")]
        if not editable_ids:
            st.info("No editable records on this page.")
            return

        selected_id = st.selectbox("Select record to edit", options=editable_ids, format_func=lambda rid: rid[:8])
        selected_row = next((r for r in page_rows if r.get("_id") == selected_id), None)
        if selected_row:
            edited_fields: dict[str, str] = {}
            edit_cols = [c for c in columns if not c.startswith("_")]
            for col in edit_cols[:10]:  # Limit to 10 fields for UI.
                edited_fields[col] = st.text_input(
                    col.replace("_", " ").title(),
                    value=str(selected_row.get(col, "") or ""),
                    key=f"edit_{selected_id}_{col}",
                )

            col_save, col_delete = st.columns(2)
            with col_save:
                if st.button("Save Changes", key=f"save_{selected_id}"):
                    update_record_fields(selected_id, edited_fields)
                    st.success("Record updated!")
                    st.rerun()
            with col_delete:
                if st.button("Delete Record", key=f"delrec_{selected_id}"):
                    delete_record(selected_id)
                    st.success("Record deleted.")
                    st.rerun()


def _render_export_section(job, records, columns):
    st.subheader("Export")

    export_format = st.selectbox(
        "Format",
        ["xlsx", "csv", "docx", "pdf", "google_sheets"],
        index=["xlsx", "csv", "docx", "pdf", "google_sheets"].index(job.get("export_format", "xlsx")) if job.get("export_format") in ["xlsx", "csv", "docx", "pdf", "google_sheets"] else 0,
        key="export_format_select",
    )

    col_e1, col_e2 = st.columns(2)
    with col_e1:
        export_scope = st.radio("Export scope", ["All records", "Selected columns only"])
    with col_e2:
        include_sources = st.checkbox("Include source URLs", value=True)
        if export_format != "google_sheets":
            selected_columns = st.multiselect("Columns to include", options=columns, default=columns)
        else:
            selected_columns = None

    if st.button("Generate Export", type="primary"):
        # Clean up records for export (remove internal keys).
        clean_records = []
        for rec in records:
            clean = {k: v for k, v in rec.items() if not k.startswith("_")}
            clean_records.append(clean)

        with st.spinner(f"Generating {export_format.upper()} export..."):
            result = export_records(
                clean_records,
                fmt=export_format,
                job_name=job.get("objective", "research")[:50],
                objective=job.get("objective", ""),
                columns=selected_columns if export_scope == "Selected columns only" else None,
                include_sources=include_sources,
            )

        if result.get("ok"):
            if result.get("path"):
                # Verify file exists.
                if os.path.exists(result["path"]):
                    create_export_job(
                        job["id"],
                        export_format,
                        len(clean_records),
                        selected_columns or columns,
                        result["path"],
                    )
                    with open(result["path"], "rb") as f:
                        st.download_button(
                            label=f"Download {export_format.upper()}",
                            data=f.read(),
                            file_name=os.path.basename(result["path"]),
                            mime="application/octet-stream",
                        )
                    st.success(f"Export ready: {os.path.basename(result['path'])} ({result.get('size', 0):,} bytes)")
                else:
                    st.error("Export file was not created.")
            elif result.get("url"):
                create_export_job(job["id"], export_format, len(clean_records), columns, destination=result["url"])
                st.success(f"Google Sheet created: [Open sheet]({result['url']})")
                st.markdown(f"**URL:** {result['url']}")
        else:
            st.error(f"Export failed: {result.get('error', 'Unknown error')}")


# ---------------------------------------------------------------------------
# Source Inspector page
# ---------------------------------------------------------------------------

def render_source_inspector():
    st.header("Source Inspector")

    job_id = st.session_state.current_job_id
    if not job_id:
        st.info("Select a job first.")
        return

    try:
        queries = get_job_search_queries(job_id)
        pages = get_job_source_pages(job_id)
    except Exception as exc:
        st.error(f"Could not load sources: {exc}")
        return

    tab_q, tab_p = st.tabs(["Search Queries", "Source Pages"])

    with tab_q:
        if not queries:
            st.info("No search queries recorded.")
        else:
            for q in queries:
                status = q.get("status", "pending")
                icon = {"completed": "✅", "running": "⏳", "failed": "❌", "pending": "⏸️"}.get(status, "❓")
                st.markdown(f"{icon} **{q['query']}** — {status} — {q.get('result_count', 0)} results")
                if q.get("error"):
                    st.caption(f"Error: {q['error']}")

    with tab_p:
        if not pages:
            st.info("No source pages recorded.")
        else:
            for p in pages:
                fetch_status = p.get("fetch_status", "pending")
                icon = {"fetched": "✅", "failed": "❌", "pending": "⏸️"}.get(fetch_status, "❓")
                with st.expander(f"{icon} {p.get('title', p['url'][:60])}"):
                    st.markdown(f"**URL:** {p['url']}")
                    st.markdown(f"**Status:** HTTP {p.get('http_status', 'N/A')} — {fetch_status}")
                    st.markdown(f"**Content length:** {p.get('content_length', 0):,} chars")
                    if p.get("retrieved_at"):
                        st.caption(f"Retrieved: {p['retrieved_at']}")
                    if p.get("error"):
                        st.error(f"Fetch error: {p['error']}")
                    if p.get("raw_content"):
                        st.text(p["raw_content"][:2000])


# ---------------------------------------------------------------------------
# Export History page
# ---------------------------------------------------------------------------

def render_export_history():
    st.header("Export History")

    job_id = st.session_state.current_job_id
    try:
        exports = list_exports(job_id if job_id else None)
    except Exception as exc:
        st.error(f"Could not load exports: {exc}")
        return

    if not exports:
        st.info("No exports yet.")
        return

    for exp in exports:
        with st.container(border=True):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.markdown(f"**{exp.get('format', '').upper()}** — {exp.get('record_count', 0)} records")
                if exp.get("destination"):
                    st.markdown(f"Destination: {exp['destination']}")
                if exp.get("file_path"):
                    st.caption(f"File: {os.path.basename(exp['file_path'])}")
            with col2:
                st.caption(f"Created: {exp.get('created_at', '')[:19]}")
            with col3:
                if exp.get("file_path") and os.path.exists(exp["file_path"]):
                    with open(exp["file_path"], "rb") as f:
                        st.download_button(
                            "Download",
                            data=f.read(),
                            file_name=os.path.basename(exp["file_path"]),
                            key=f"dl_{exp['id']}",
                        )


# ---------------------------------------------------------------------------
# Page routing
# ---------------------------------------------------------------------------

if page == "New Research":
    render_new_research()
elif page == "Job History":
    render_job_history()
elif page == "Results & Export":
    render_results()
elif page == "Source Inspector":
    render_source_inspector()
elif page == "Export History":
    render_export_history()
elif page == "Connection Status":
    render_connection_status()
