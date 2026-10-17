"""CSV export with proper quoting and formula-injection protection."""

from __future__ import annotations

import csv
import io
import os
from typing import Any

from exports.common import collect_columns, ensure_temp_dir, generate_filename
from utils.security import sanitize_cell_value


def export_to_csv(
    records: list[dict[str, Any]],
    job_name: str,
    columns: list[str] | None = None,
    include_sources: bool = True,
) -> str:
    """Export records to a UTF-8 CSV file. Returns the file path."""
    cols = collect_columns(records, columns)
    if not cols:
        cols = list(records[0].keys()) if records else []

    temp_dir = ensure_temp_dir()
    filename = generate_filename(job_name, "csv")
    filepath = os.path.join(temp_dir, filename)

    # Use io.StringIO then write as UTF-8 with BOM for Excel compatibility.
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")

    # Header
    writer.writerow([c.replace("_", " ").title() for c in cols])

    for record in records:
        row: list[str] = []
        for col in cols:
            value = record.get(col, "")
            if value is None:
                value = ""
            row.append(sanitize_cell_value(str(value)))
        writer.writerow(row)

    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        f.write(buffer.getvalue())

    return filepath
