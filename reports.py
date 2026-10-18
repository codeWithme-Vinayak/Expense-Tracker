"""Exporting reports to CSV and Excel files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import analysis
import config


class ExportError(Exception):
    """Raised when a report cannot be written."""


def _printable(df: pd.DataFrame) -> pd.DataFrame:
    """Transactions in a clean, human-friendly layout."""
    out = df.sort_values(["date", "id"]).copy()
    out["date"] = out["date"].dt.strftime(config.DATE_FORMAT)
    out = out.rename(columns={
        "id": "ID", "date": "Date", "type": "Type", "category": "Category",
        "description": "Description", "amount": f"Amount ({config.CURRENCY})",
    })
    return out


def export_csv(df: pd.DataFrame, path) -> Path:
    """Write the given transactions to a CSV file."""
    path = Path(path)
    try:
        # utf-8-sig so Excel shows the rupee sign correctly when opening it.
        _printable(df).to_csv(path, index=False, encoding="utf-8-sig")
    except OSError as exc:
        raise ExportError(f"Could not write {path.name}: {exc}") from exc
    return path


def export_excel(df: pd.DataFrame, path) -> Path:
    """Write an Excel workbook with three sheets: Transactions,
    Category Summary and Monthly Summary."""
    path = Path(path)
    try:
        import openpyxl  # noqa: F401  (only checking that it is installed)
    except ImportError:
        raise ExportError(
            "Excel export needs the 'openpyxl' package.\n"
            "Install it with:  pip install openpyxl"
        ) from None

    categories = analysis.category_summary(df).reset_index()
    categories.columns = ["Category", f"Amount ({config.CURRENCY})"]
    total = categories[f"Amount ({config.CURRENCY})"].sum()
    categories["Share (%)"] = (
        (categories[f"Amount ({config.CURRENCY})"] / total * 100).round(1)
        if total else 0.0
    )

    monthly = analysis.monthly_summary(df).reset_index()
    monthly.columns = ["Month", "Income", "Expense", "Savings"]

    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            sheets = {
                "Transactions": _printable(df),
                "Category Summary": categories,
                "Monthly Summary": monthly,
            }
            for name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=name, index=False)
                sheet = writer.sheets[name]
                for column in sheet.columns:
                    longest = max(len(str(cell.value or "")) for cell in column)
                    sheet.column_dimensions[column[0].column_letter].width = (
                        min(max(longest + 3, 12), 45)
                    )
    except (OSError, PermissionError) as exc:
        raise ExportError(
            f"Could not write {path.name}. Is it open in Excel?\n{exc}"
        ) from exc
    return path
