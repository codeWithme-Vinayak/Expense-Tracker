"""Automated tests for the Expense Tracker (Testing module).

Run from the project folder with:

    python -m unittest discover -s tests -v

The tests use a temporary folder, so your real data is never touched.
"""

import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analysis      # noqa: E402
import config        # noqa: E402
import reports       # noqa: E402
import validators    # noqa: E402
from storage import ExpenseStore, StorageError   # noqa: E402


def make_record(day="2026-09-10", tx_type="Expense", category="Food",
                description="Lunch", amount=100.0):
    return {"date": datetime.strptime(day, "%Y-%m-%d"), "type": tx_type,
            "category": category, "description": description, "amount": amount}


# ---------------------------------------------------------------- validators
class ValidatorTests(unittest.TestCase):
    def test_amount_accepts_valid_numbers(self):
        self.assertEqual(validators.validate_amount("250"), 250.0)
        self.assertEqual(validators.validate_amount(" 1,250.456 "), 1250.46)
        self.assertEqual(validators.validate_amount("₹99.5"), 99.5)

    def test_amount_rejects_bad_input(self):
        for bad in ["", "   ", "abc", "-5", "0", "nan", "inf", "1e99", None]:
            with self.subTest(bad=bad):
                with self.assertRaises(validators.ValidationError):
                    validators.validate_amount(bad)

    def test_date_format_and_future(self):
        self.assertEqual(validators.validate_date("2026-01-31"), datetime(2026, 1, 31))
        for bad in ["", "31-01-2026", "2026-13-01", "2026-02-30", "yesterday"]:
            with self.subTest(bad=bad):
                with self.assertRaises(validators.ValidationError):
                    validators.validate_date(bad)
        tomorrow = (date.today() + timedelta(days=1)).strftime(config.DATE_FORMAT)
        with self.assertRaises(validators.ValidationError):
            validators.validate_date(tomorrow)
        self.assertIsNotNone(validators.validate_date(tomorrow, allow_future=True))

    def test_category_must_match_type(self):
        self.assertEqual(validators.validate_category("Food", "Expense"), "Food")
        self.assertEqual(validators.validate_category("Salary", "Income"), "Salary")
        with self.assertRaises(validators.ValidationError):
            validators.validate_category("Salary", "Expense")
        with self.assertRaises(validators.ValidationError):
            validators.validate_category("Food", "Income")

    def test_description_is_cleaned_and_limited(self):
        self.assertEqual(validators.validate_description("  tea   and  snacks "), "tea and snacks")
        self.assertEqual(validators.validate_description(None), "")
        with self.assertRaises(validators.ValidationError):
            validators.validate_description("x" * 61)

    def test_budget_allows_zero_but_not_negative(self):
        self.assertEqual(validators.validate_budget("0"), 0.0)
        self.assertEqual(validators.validate_budget("6,500"), 6500.0)
        for bad in ["", "-1", "abc"]:
            with self.assertRaises(validators.ValidationError):
                validators.validate_budget(bad)

    def test_validate_transaction_returns_clean_record(self):
        record = validators.validate_transaction(
            "2026-09-10", "Expense", "Travel", " Metro  ", "45")
        self.assertEqual(record["amount"], 45.0)
        self.assertEqual(record["description"], "Metro")
        self.assertEqual(record["date"], datetime(2026, 9, 10))


# ------------------------------------------------------------------- storage
class StorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.csv = self.folder / "expenses.csv"
        self.budget = self.folder / "budget.json"
        self.store = ExpenseStore(self.csv, self.budget)

    def tearDown(self):
        self._tmp.cleanup()

    def test_starts_empty(self):
        self.assertTrue(self.store.df.empty)
        self.assertEqual(list(self.store.df.columns), config.COLUMNS)

    def test_add_assigns_increasing_ids_and_persists(self):
        first = self.store.add(make_record())
        second = self.store.add(make_record(amount=50))
        self.assertEqual((first, second), (1, 2))
        reloaded = ExpenseStore(self.csv, self.budget)
        self.assertEqual(len(reloaded.df), 2)
        self.assertEqual(reloaded.get(2)["amount"], 50.0)

    def test_update_changes_only_the_chosen_row(self):
        self.store.add(make_record())
        self.store.add(make_record(amount=70))
        self.store.update(1, make_record(category="Travel", description="Bus", amount=30))
        self.assertEqual(self.store.get(1)["category"], "Travel")
        self.assertEqual(self.store.get(1)["amount"], 30.0)
        self.assertEqual(self.store.get(2)["amount"], 70.0)

    def test_delete_removes_row_and_ids_are_not_reused_badly(self):
        self.store.add(make_record())
        self.store.add(make_record(amount=70))
        self.store.delete(1)
        self.assertEqual(len(self.store.df), 1)
        self.assertEqual(self.store.add(make_record()), 3)

    def test_missing_id_raises(self):
        with self.assertRaises(StorageError):
            self.store.get(99)
        with self.assertRaises(StorageError):
            self.store.update(99, make_record())
        with self.assertRaises(StorageError):
            self.store.delete(99)

    def test_returned_dataframe_is_a_copy(self):
        self.store.add(make_record())
        frame = self.store.df
        frame.loc[0, "amount"] = 999999
        self.assertEqual(self.store.get(1)["amount"], 100.0)

    def test_corrupt_rows_are_skipped_and_bad_files_reported(self):
        self.csv.write_text(
            "id,date,type,category,description,amount\n"
            "1,2026-09-01,Expense,Food,ok,10\n"
            "2,not-a-date,Expense,Food,broken,10\n"
            "3,2026-09-03,Expense,Food,broken amount,abc\n")
        self.assertEqual(len(ExpenseStore(self.csv, self.budget).df), 1)
        self.csv.write_text("wrong,columns\n1,2\n")
        with self.assertRaises(StorageError):
            ExpenseStore(self.csv, self.budget)

    def test_budget_month_overrides_default(self):
        self.assertEqual(self.store.get_budget("2026-09"), 0.0)
        self.store.set_budget(5000)                    # default
        self.store.set_budget(7000, "2026-09")         # one month
        self.assertEqual(self.store.get_budget("2026-09"), 7000.0)
        self.assertEqual(self.store.get_budget("2026-08"), 5000.0)
        self.store.set_budget(0, "2026-09")            # remove override
        self.assertEqual(self.store.get_budget("2026-09"), 5000.0)

    def test_damaged_budget_file_falls_back_safely(self):
        self.budget.write_text("{not json")
        self.assertEqual(self.store.get_budget("2026-09"), 0.0)


# ------------------------------------------------------------------ analysis
class AnalysisTests(unittest.TestCase):
    def setUp(self):
        rows = [
            make_record("2026-08-05", "Income", "Pocket Money", "Aug money", 8000),
            make_record("2026-08-10", "Expense", "Food", "Lunch", 200),
            make_record("2026-09-01", "Income", "Pocket Money", "Sep money", 8000),
            make_record("2026-09-02", "Expense", "Food", "Tea", 50),
            make_record("2026-09-02", "Expense", "Travel", "Auto", 150),
            make_record("2026-09-15", "Expense", "Shopping", "Shirt", 1000),
            make_record("2026-09-15", "Expense", "Food", "Dinner", 300),
        ]
        with tempfile.TemporaryDirectory() as folder:
            store = ExpenseStore(Path(folder) / "e.csv", Path(folder) / "b.json")
            for row in rows:
                store.add(row)
            self.df = store.df

    def test_totals(self):
        self.assertEqual(analysis.totals(self.df),
                         {"income": 16000.0, "expense": 1700.0, "savings": 14300.0})
        self.assertEqual(analysis.totals(self.df.iloc[0:0]),
                         {"income": 0.0, "expense": 0.0, "savings": 0.0})

    def test_filters(self):
        sept = analysis.filter_transactions(self.df, month="2026-09")
        self.assertEqual(len(sept), 5)
        self.assertEqual(len(analysis.filter_transactions(self.df, category="Food")), 3)
        self.assertEqual(len(analysis.filter_transactions(self.df, tx_type="Income")), 2)
        self.assertEqual(len(analysis.filter_transactions(self.df, keyword="DINNER")), 1)
        self.assertEqual(len(analysis.filter_transactions(
            self.df, start="2026-09-02", end="2026-09-15")), 4)
        self.assertEqual(len(analysis.filter_transactions(self.df, category="All")), 7)
        self.assertEqual(len(analysis.filter_transactions(self.df, keyword="zzz")), 0)

    def test_category_summary_sorted_and_expense_only(self):
        summary = analysis.category_summary(self.df)
        self.assertEqual(summary.to_dict(),
                         {"Shopping": 1000.0, "Food": 550.0, "Travel": 150.0})
        self.assertEqual(list(summary.index)[0], "Shopping")
        self.assertTrue(analysis.category_summary(self.df.iloc[0:0]).empty)

    def test_monthly_summary(self):
        table = analysis.monthly_summary(self.df)
        self.assertEqual(list(table.index), ["2026-08", "2026-09"])
        self.assertEqual(table.loc["2026-09", "Expense"], 1500.0)
        self.assertEqual(table.loc["2026-09", "Savings"], 6500.0)
        self.assertEqual(table.loc["2026-08", "Savings"], 7800.0)
        self.assertTrue(analysis.monthly_summary(self.df.iloc[0:0]).empty)

    def test_monthly_summary_with_only_income(self):
        only_income = self.df[self.df["type"] == "Income"]
        table = analysis.monthly_summary(only_income)
        self.assertEqual(table["Expense"].sum(), 0.0)

    def test_daily_spending_uses_only_the_chosen_month(self):
        daily = analysis.daily_spending(self.df, "2026-09")
        self.assertEqual(len(daily), 30)
        self.assertEqual(daily.loc[2], 200.0)
        self.assertEqual(daily.loc[15], 1300.0)
        self.assertEqual(daily.sum(), 1500.0)          # August's 200 is not mixed in
        self.assertEqual(analysis.daily_spending(self.df, "2026-08").sum(), 200.0)

    def test_daily_spending_stops_today_for_current_month(self):
        today = date.today()
        key = analysis.month_key(today)
        empty = self.df.iloc[0:0]
        self.assertEqual(len(analysis.daily_spending(empty, key)), today.day)

    def test_budget_status_levels(self):
        # September spending in the sample data is 1500.
        ok = analysis.budget_status(self.df, "2026-09", 3000)          # 50% used
        self.assertEqual(ok["status"], "ok")
        self.assertAlmostEqual(ok["percent"], 50.0)
        self.assertEqual(ok["remaining"], 1500.0)

        cases = [
            (0, "not_set"),        # no budget
            (3000, "ok"),          # 50%
            (1875, "warning"),     # exactly 80%
            (1800, "warning"),     # 83%
            (1500, "warning"),     # exactly 100% is still within budget
            (1499, "over"),        # one rupee over
        ]
        for budget, expected in cases:
            with self.subTest(budget=budget):
                self.assertEqual(
                    analysis.budget_status(self.df, "2026-09", budget)["status"], expected)

        # Only that month's spending counts (August's 200 is ignored).
        self.assertEqual(analysis.budget_status(self.df, "2026-08", 1000)["spent"], 200.0)

    def test_available_months_newest_first(self):
        self.assertEqual(analysis.available_months(self.df), ["2026-09", "2026-08"])
        self.assertEqual(analysis.available_months(self.df.iloc[0:0]), [])

    def test_format_inr_uses_indian_grouping(self):
        self.assertEqual(analysis.format_inr(0), "₹0.00")
        self.assertEqual(analysis.format_inr(999), "₹999.00")
        self.assertEqual(analysis.format_inr(1000), "₹1,000.00")
        self.assertEqual(analysis.format_inr(123456.5), "₹1,23,456.50")
        self.assertEqual(analysis.format_inr(12345678), "₹1,23,45,678.00")
        self.assertEqual(analysis.format_inr(-1500.5), "-₹1,500.50")
        self.assertEqual(analysis.format_inr(100000, 0), "₹1,00,000")

    def test_month_helpers(self):
        self.assertEqual(analysis.month_key(datetime(2026, 10, 11)), "2026-10")
        self.assertEqual(analysis.month_label("2026-10"), "October 2026")


# ------------------------------------------------------------------- reports
class ReportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        store = ExpenseStore(self.folder / "e.csv", self.folder / "b.json")
        store.add(make_record("2026-09-01", "Income", "Pocket Money", "Money", 8000))
        store.add(make_record("2026-09-02", "Expense", "Food", "Tea", 50))
        store.add(make_record("2026-09-03", "Expense", "Travel", "Auto", 150))
        self.df = store.df

    def tearDown(self):
        self._tmp.cleanup()

    def test_csv_export_round_trip(self):
        path = reports.export_csv(self.df, self.folder / "out.csv")
        back = pd.read_csv(path, encoding="utf-8-sig")
        self.assertEqual(len(back), 3)
        self.assertIn(f"Amount ({config.CURRENCY})", back.columns)

    def test_excel_export_has_three_sheets(self):
        path = reports.export_excel(self.df, self.folder / "out.xlsx")
        sheets = pd.read_excel(path, sheet_name=None)
        self.assertEqual(list(sheets), ["Transactions", "Category Summary", "Monthly Summary"])
        self.assertEqual(len(sheets["Transactions"]), 3)
        self.assertEqual(sheets["Monthly Summary"].loc[0, "Savings"], 7800)

    def test_export_to_missing_folder_gives_clear_error(self):
        with self.assertRaises(reports.ExportError):
            reports.export_csv(self.df, self.folder / "no_such_folder" / "x.csv")


if __name__ == "__main__":
    unittest.main()
