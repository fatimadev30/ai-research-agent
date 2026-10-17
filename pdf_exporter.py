"""PDF export using ReportLab Platypus."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.platypus.flowables import HRFlowable

from exports.common import collect_columns, ensure_temp_dir, generate_filename


def export_to_pdf(
    records: list[dict[str, Any]],
    job_name: str,
    objective: str = "",
    columns: list[str] | None = None,
    include_sources: bool = True,
    max_table_rows: int = 40,
) -> str:
    """Export a structured research report to PDF. Returns the file path."""
    cols = collect_columns(records, columns)
    if not cols:
        cols = list(records[0].keys()) if records else []

    temp_dir = ensure_temp_dir()
    filename = generate_filename(job_name, "pdf")
    filepath = os.path.join(temp_dir, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=landscape(A4),
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading1"]
    body_style = styles["BodyText"]
    link_style = ParagraphStyle("Link", parent=body_style, textColor=colors.HexColor("#2563EB"))
    cell_style = ParagraphStyle("Cell", parent=body_style, fontSize=8, leading=10)
    header_style = ParagraphStyle("Header", parent=body_style, fontSize=8, leading=10, textColor=colors.white, fontName="Helvetica-Bold")

    story: list[Any] = []

    # -- Title --
    story.append(Paragraph(job_name or "Research Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", body_style))
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%"))
    story.append(Spacer(1, 12))

    # -- Objective --
    if objective:
        story.append(Paragraph("Research Objective", heading_style))
        story.append(Paragraph(_escape(objective), body_style))
        story.append(Spacer(1, 10))

    # -- Summary --
    story.append(Paragraph("Executive Summary", heading_style))
    story.append(Paragraph(
        f"This report contains {len(records)} records extracted from web research. "
        f"The data was collected using automated web search and page analysis.",
        body_style,
    ))
    story.append(Spacer(1, 10))

    # -- Data Table --
    story.append(Paragraph("Extracted Records", heading_style))
    story.append(Spacer(1, 6))

    display_cols = cols[:8]  # Limit columns to fit page.
    display_rows = min(len(records), max_table_rows)

    if display_rows > 0:
        # Build table data.
        table_data = [[Paragraph(c.replace("_", " ").title(), header_style) for c in display_cols]]
        for record in records[:display_rows]:
            row = []
            for col in display_cols:
                val = record.get(col, "")
                if val is None:
                    val = ""
                val_str = str(val)[:150]
                if col in ("source_url", "website", "linkedin_url", "profile_url") and val_str.startswith("http"):
                    row.append(Paragraph(f'<a href="{val_str}">{_escape(val_str[:50])}</a>', cell_style))
                else:
                    row.append(Paragraph(_escape(val_str), cell_style))
            table_data.append(row)

        # Calculate column widths to fit page.
        page_width = landscape(A4)[0] - inch
        col_width = page_width / len(display_cols)
        col_widths = [col_width] * len(display_cols)

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

        if len(records) > max_table_rows:
            story.append(Spacer(1, 8))
            story.append(Paragraph(
                f"Showing first {max_table_rows} of {len(records)} records. "
                "See the spreadsheet export for the complete dataset.",
                body_style,
            ))
    else:
        story.append(Paragraph("No records were found.", body_style))

    # -- Sources --
    if include_sources and records:
        story.append(PageBreak())
        story.append(Paragraph("Source References", heading_style))
        story.append(Spacer(1, 6))
        seen_urls: set[str] = set()
        for record in records:
            url = record.get("source_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                story.append(Paragraph(f'<a href="{_escape(url)}">{_escape(url)}</a>', link_style))
                story.append(Spacer(1, 2))

    # -- Limitations --
    story.append(Spacer(1, 12))
    story.append(Paragraph("Limitations", heading_style))
    story.append(Paragraph(
        "Missing fields indicate information was not available on source pages. "
        "No data was fabricated. All values are grounded in fetched content.",
        body_style,
    ))

    # Build with page numbers.
    def _add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        page_num = canvas.getPageNumber()
        canvas.drawRightString(landscape(A4)[0] - 0.5 * inch, 0.3 * inch, f"Page {page_num}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    return filepath


def _escape(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraphs."""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
