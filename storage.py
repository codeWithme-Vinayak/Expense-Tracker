"""Data storage (Data Storage module).

All transactions live in a Pandas DataFrame in memory and are saved to a
single CSV file after every change. The monthly budget is kept in a tiny
JSON file next to it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

import config


class StorageError(Exception):
    """Raised when the data files cannot be read or written."""


class ExpenseStore:
    """Create, read, update and delete transactions."""

    def __init__(self, csv_path=config.EXPENSES_FILE, budget_path=config.BUDGET_FILE):
        self.csv_path = Path(csv_path)
        self.budget_path = Path(budget_path)
        try:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(f"Cannot create data folder: {exc}") from exc
        self._df = self._load()

    # ------------------------------------------------------------- internals
    @staticmethod
    def _normalise(df: pd.DataFrame) -> pd.DataFrame:
        """Force every column to the correct data type."""
        df = df.reindex(columns=config.COLUMNS).copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df["id"] = pd.to_numeric(df["id"], errors="coerce")
        df["description"] = df["description"].fillna("").astype(str)
        df["type"] = df["type"].astype(str)
        df["category"] = df["category"].astype(str)
        # Drop rows that are damaged beyond repair (e.g. hand-edited badly).
        df = df.dropna(subset=["id", "date", "amount"])
        df["id"] = df["id"].astype("int64")
        df["amount"] = df["amount"].astype("float64")
        return df.reset_index(drop=True)

    def _load(self) -> pd.DataFrame:
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            return self._normalise(pd.DataFrame(columns=config.COLUMNS))
        try:
            raw = pd.read_csv(self.csv_path)
        except Exception as exc:  # unreadable / corrupt file
            raise StorageError(f"Could not read {self.csv_path.name}: {exc}") from exc
        missing = set(config.COLUMNS) - set(raw.columns)
        if missing:
            raise StorageError(
                f"{self.csv_path.name} is missing columns: {', '.join(sorted(missing))}"
            )
        return self._normalise(raw)

    def _save(self) -> None:
        out = self._df.copy()
        out["date"] = out["date"].dt.strftime(config.DATE_FORMAT)
        temp = self.csv_path.with_suffix(".tmp")
        try:
            out.to_csv(temp, index=False)
            os.replace(temp, self.csv_path)      # atomic: never a half-written file
        except OSError as exc:
            raise StorageError(
                f"Could not save {self.csv_path.name}. Is it open in another program?\n{exc}"
            ) from exc

    def _rebuild(self, rows: list) -> None:
        self._df = self._normalise(pd.DataFrame(rows, columns=config.COLUMNS))
        self._save()

    # ------------------------------------------------------------ public API
    @property
    def df(self) -> pd.DataFrame:
        """A copy of all transactions (changing it does not change the store)."""
        return self._df.copy()

    def get(self, tx_id: int) -> dict:
        match = self._df[self._df["id"] == tx_id]
        if match.empty:
            raise StorageError(f"Transaction {tx_id} was not found.")
        return match.iloc[0].to_dict()

    def add(self, record: dict) -> int:
        """Add a validated record and return its new id."""
        new_id = int(self._df["id"].max()) + 1 if not self._df.empty else 1
        rows = self._df.to_dict("records")
        rows.append({"id": new_id, **record})
        self._rebuild(rows)
        return new_id

    def update(self, tx_id: int, record: dict) -> None:
        rows = self._df.to_dict("records")
        for row in rows:
            if row["id"] == tx_id:
                row.update(record)
                break
        else:
            raise StorageError(f"Transaction {tx_id} was not found.")
        self._rebuild(rows)

    def delete(self, tx_id: int) -> None:
        rows = [r for r in self._df.to_dict("records") if r["id"] != tx_id]
        if len(rows) == len(self._df):
            raise StorageError(f"Transaction {tx_id} was not found.")
        self._rebuild(rows)

    # ---------------------------------------------------------------- budget
    def _read_budget_file(self) -> dict:
        if not self.budget_path.exists():
            return {"default": 0.0, "months": {}}
        try:
            data = json.loads(self.budget_path.read_text(encoding="utf-8"))
            return {
                "default": float(data.get("default", 0.0)),
                "months": {str(k): float(v) for k, v in data.get("months", {}).items()},
            }
        except (ValueError, OSError, AttributeError):
            return {"default": 0.0, "months": {}}   # damaged file: start fresh

    def get_budget(self, month: str | None = None) -> float:
        """Budget for ``month`` ("YYYY-MM"); falls back to the default budget."""
        data = self._read_budget_file()
        if month and month in data["months"]:
            return data["months"][month]
        return data["default"]

    def set_budget(self, amount: float, month: str | None = None) -> None:
        """Set the budget for one month, or the default for all months if
        ``month`` is None. An amount of 0 removes that budget."""
        data = self._read_budget_file()
        if month:
            if amount > 0:
                data["months"][month] = amount
            else:
                data["months"].pop(month, None)
        else:
            data["default"] = amount
        try:
            self.budget_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            raise StorageError(f"Could not save the budget: {exc}") from exc
