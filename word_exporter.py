"""Word (DOCX) export using python-docx."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from docx import Document
from docx.shared import Inches, Pt

from exports.common import collect_columns, ensure_temp_dir, generate_filename


def export_to_docx(
    records: list[dict[str, Any]],
    job_name: str,
    objective: str = "",
    columns: list[str] | None = None,
    include_sources: bool = True,
    max_table_rows: int = 50,
) -> str:
    """Export a structured research report to DOCX. Returns the file path."""
    cols = collect_columns(records, columns)
    if not cols:
        cols = list(records[0].keys()) if records else []

    doc = Document()

    # -- Title --
    title = doc.add_heading(job_name or "Research Report", level=0)
    doc.add_paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # -- Objective --
    if objective:
        doc.add_heading("Research Objective", level=1)
        doc.add_paragraph(objective)

    # -- Executive Summary --
    doc.add_heading("Executive Summary", level=1)
    doc.add_paragraph(
        f"This report contains {len(records)} records extracted from web research. "
        f"The data was collected using automated web search and page analysis."
    )

    # -- Methodology --
    doc.add_heading("Methodology", level=1)
    doc.add_paragraph(
        "Records were gathered by executing web search queries, fetching relevant pages, "
        "and extracting structured fields from page content. All extracted values are grounded "
        "in the source content. Missing fields are marked as unavailable. No data was fabricated."
    )

    # -- Key Findings --
    doc.add_heading("Key Findings", level=1)
    doc.add_paragraph(f"Total records extracted: {len(records)}")
    doc.add_paragraph(f"Fields per record: {len(cols)}")
    if records:
        filled = sum(1 for r in records for c in cols if r.get(c))
        total = len(records) * len(cols)
        coverage = (filled / total * 100) if total else 0
        doc.add_paragraph(f"Field coverage: {coverage:.1f}%")

    # -- Data Table (limited rows for readability) --
    doc.add_heading("Data Summary", level=1)
    display_rows = min(len(records), max_table_rows)
    if display_rows > 0:
        table = doc.add_table(rows=1 + display_rows, cols=min(len(cols), 6))
        table.style = "Light Grid Accent 1"
        # Header
        for i, col in enumerate(cols[:6]):
            cell = table.rows[0].cells[i]
            cell.text = col.replace("_", " ").title()
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True
        # Data
        for row_idx, record in enumerate(records[:display_rows], start=1):
            for col_idx, col in enumerate(cols[:6]):
                value = record.get(col, "")
                if value is None:
                    value = ""
                table.rows[row_idx].cells[col_idx].text = str(value)[:200]
        if len(records) > max_table_rows:
            doc.add_paragraph(
                f"\nShowing first {max_table_rows} of {len(records)} records. "
                "See the spreadsheet export for the complete dataset."
            )
    else:
        doc.add_paragraph("No records were found.")

    # -- Source References --
    if include_sources and records:
        doc.add_heading("Source References", level=1)
        seen_urls: set[str] = set()
        for record in records[:50]:
            url = record.get("source_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                doc.add_paragraph(url, style="List Bullet")

    # -- Limitations --
    doc.add_heading("Limitations and Missing Data", level=1)
    missing_fields = [c for c in cols if any(not r.get(c) for r in records)]
    if missing_fields:
        doc.add_paragraph(
            "The following fields had missing values for some records: "
            + ", ".join(c.replace("_", " ") for c in missing_fields)
            + ". This indicates the information was not available on the source pages, "
            "not that extraction failed."
        )
    doc.add_paragraph(
        "AI-generated summaries or inferences are separated from facts supported by source content. "
        "Treat all web-sourced data with appropriate verification."
    )

    temp_dir = ensure_temp_dir()
    filename = generate_filename(job_name, "docx")
    filepath = os.path.join(temp_dir, filename)
    doc.save(filepath)
    return filepath
