"""Data processing (Data Processing module).

Pure functions that take the transactions DataFrame and return filtered
data or summaries. Nothing here touches the screen or the disk, which makes
every function easy to test on its own.
"""

from __future__ import annotations

import calendar
from datetime import date

import pandas as pd

import config


# --------------------------------------------------------------- formatting
def format_inr(amount, decimals: int = 2) -> str:
    """Format a number the Indian way: 1234567.5 -> '₹12,34,567.50'."""
    amount = float(amount)
    sign = "-" if amount < 0 else ""
    amount = abs(round(amount, decimals))
    whole, _, frac = f"{amount:.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    result = f"{sign}{config.CURRENCY}{whole}"
    return f"{result}.{frac}" if decimals else result


def month_key(value) -> str:
    """'2026-10' for a date / Timestamp / datetime."""
    return pd.Timestamp(value).strftime(config.MONTH_FORMAT)


def month_label(key: str) -> str:
    """'2026-10' -> 'October 2026'."""
    return pd.Timestamp(f"{key}-01").strftime("%B %Y")


# ---------------------------------------------------------------- filtering
def filter_transactions(
    df: pd.DataFrame,
    start=None,
    end=None,
    category: str | None = None,
    tx_type: str | None = None,
    keyword: str | None = None,
    month: str | None = None,
) -> pd.DataFrame:
    """Return the rows that match every filter that was given."""
    out = df
    if month:
        out = out[out["date"].dt.strftime(config.MONTH_FORMAT) == month]
    if start is not None:
        out = out[out["date"] >= pd.Timestamp(start)]
    if end is not None:
        out = out[out["date"] <= pd.Timestamp(end)]
    if category and category != "All":
        out = out[out["category"] == category]
    if tx_type and tx_type != "All":
        out = out[out["type"] == tx_type]
    if keyword and keyword.strip():
        kw = keyword.strip().lower()
        hit = (
            out["description"].str.lower().str.contains(kw, regex=False)
            | out["category"].str.lower().str.contains(kw, regex=False)
        )
        out = out[hit]
    return out.copy()


def available_months(df: pd.DataFrame) -> list[str]:
    """All months that have data, newest first."""
    if df.empty:
        return []
    months = df["date"].dt.strftime(config.MONTH_FORMAT).unique().tolist()
    return sorted(months, reverse=True)


# ---------------------------------------------------------------- summaries
def totals(df: pd.DataFrame) -> dict:
    """Total income, total expense and savings (income - expense)."""
    income = float(df.loc[df["type"] == config.INCOME, "amount"].sum())
    expense = float(df.loc[df["type"] == config.EXPENSE, "amount"].sum())
    return {"income": income, "expense": expense, "savings": income - expense}


def category_summary(df: pd.DataFrame) -> pd.Series:
    """Expense total per category, largest first."""
    spent = df[df["type"] == config.EXPENSE]
    if spent.empty:
        return pd.Series(dtype="float64", name="amount")
    return (
        spent.groupby("category")["amount"].sum()
        .sort_values(ascending=False)
        .rename("amount")
    )


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per month with Income, Expense and Savings columns."""
    columns = ["Income", "Expense", "Savings"]
    if df.empty:
        return pd.DataFrame(columns=columns, dtype="float64")
    data = df.assign(month=df["date"].dt.strftime(config.MONTH_FORMAT))
    table = data.pivot_table(
        index="month", columns="type", values="amount",
        aggfunc="sum", fill_value=0.0,
    )
    table = table.reindex(columns=["Income", "Expense"], fill_value=0.0)
    table["Savings"] = table["Income"] - table["Expense"]
    return table.sort_index().astype("float64")


def daily_spending(df: pd.DataFrame, month: str | None = None) -> pd.Series:
    """Expense total per day. For a given month every day up to the end of
    the month (or up to today, for the current month) is included; days
    without spending show 0. The result is indexed by day-of-month."""
    spent = df[df["type"] == config.EXPENSE]
    if month:
        spent = filter_transactions(spent, month=month)   # only this month's rows
        year, mon = int(month[:4]), int(month[5:7])
        days = calendar.monthrange(year, mon)[1]
        if month == month_key(date.today()):
            days = date.today().day           # don't draw days that haven't happened yet
        per_day = spent.groupby(spent["date"].dt.day)["amount"].sum()
        return per_day.reindex(range(1, days + 1), fill_value=0.0).astype("float64")
    if spent.empty:
        return pd.Series(dtype="float64")
    return spent.groupby(spent["date"].dt.normalize())["amount"].sum()


def budget_status(df: pd.DataFrame, month: str, budget: float) -> dict:
    """How much of ``budget`` has been spent in ``month``.

    status is one of: 'not_set', 'ok', 'warning' (>= 80% used), 'over'.
    """
    month_rows = filter_transactions(df, month=month)
    spent = totals(month_rows)["expense"]
    if budget <= 0:
        return {"status": "not_set", "budget": 0.0, "spent": spent,
                "remaining": 0.0, "percent": 0.0}
    percent = spent / budget * 100
    if spent > budget:
        status = "over"
    elif spent >= budget * config.BUDGET_WARNING_RATIO:
        status = "warning"
    else:
        status = "ok"
    return {"status": status, "budget": budget, "spent": spent,
            "remaining": budget - spent, "percent": percent}
