"""Fill the Expense Tracker with realistic demo data.

Usage:
    python generate_sample_data.py            # create demo data (3 months)
    python generate_sample_data.py --force    # replace existing data

The data ends today, so the charts always look current. To start fresh
with your own data later, just delete the files inside the 'data' folder.
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta

import config
from storage import ExpenseStore

DAYS = 92          # about three months of history
SEED = 42          # same seed -> same demo data every time

FOOD = ["Canteen lunch", "Tea and snacks", "Dinner", "Breakfast", "Juice", "Pizza with friends"]
TRAVEL = ["Auto fare", "Metro card recharge", "Bus ticket", "Cab to college", "Petrol"]
SHOPPING = ["Clothes", "Stationery", "Headphones", "Shoes", "Backpack", "Books"]
HEALTH = ["Medicines", "Doctor visit", "Vitamins"]
OTHER = ["Mobile recharge", "Printouts", "Gift", "Haircut", "Internet bill"]


def build_records(today: date) -> list[dict]:
    rng = random.Random(SEED)
    records: list[dict] = []

    def add(day: date, tx_type: str, category: str, description: str, amount: float):
        records.append({
            "date": datetime.combine(day, datetime.min.time()),
            "type": tx_type, "category": category,
            "description": description, "amount": round(amount, 2),
        })

    for offset in range(DAYS, -1, -1):
        day = today - timedelta(days=offset)

        # Money coming in: pocket money on the 1st, a little extra now and then.
        if day.day == 1 or offset == DAYS:      # 1st of the month (and day one)
            add(day, config.INCOME, "Pocket Money", "Monthly pocket money", 8000)
        if day.day == 15 and rng.random() < 0.6:
            add(day, config.INCOME, "Other", "Tutoring payment", rng.choice([500, 800, 1000]))

        # Money going out.
        if rng.random() < 0.85:
            add(day, config.EXPENSE, "Food", rng.choice(FOOD), rng.randint(40, 220))
        if rng.random() < 0.35:
            add(day, config.EXPENSE, "Travel", rng.choice(TRAVEL), rng.randint(20, 200))
        if rng.random() < 0.06:
            add(day, config.EXPENSE, "Shopping", rng.choice(SHOPPING), rng.randint(300, 1500))
        if rng.random() < 0.03:
            add(day, config.EXPENSE, "Health", rng.choice(HEALTH), rng.randint(100, 600))
        if rng.random() < 0.08:
            add(day, config.EXPENSE, "Other", rng.choice(OTHER), rng.randint(50, 400))
    return records


def main() -> int:
    force = "--force" in sys.argv
    if config.EXPENSES_FILE.exists() and config.EXPENSES_FILE.stat().st_size > 0 and not force:
        print("Data already exists. Run with --force to replace it.")
        return 1
    if force:
        for path in (config.EXPENSES_FILE, config.BUDGET_FILE):
            path.unlink(missing_ok=True)

    store = ExpenseStore()
    for record in build_records(date.today()):
        store.add(record)
    store.set_budget(6500)
    print(f"Created {len(store.df)} demo transactions and a default budget of 6,500.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
