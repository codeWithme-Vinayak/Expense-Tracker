"""Central configuration for the Expense Tracker project.

Everything that other modules need to agree on (file locations, category
names, date format, currency symbol) lives here, so a change only has to be
made in one place.
"""

from pathlib import Path

# ---------------------------------------------------------------- file paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPENSES_FILE = DATA_DIR / "expenses.csv"
BUDGET_FILE = DATA_DIR / "budget.json"

# ------------------------------------------------------------------ settings
APP_TITLE = "Expense Tracker"
CURRENCY = "₹"               # Indian Rupee sign
DATE_FORMAT = "%Y-%m-%d"          # how dates are typed and stored (2026-10-11)
MONTH_FORMAT = "%Y-%m"            # internal month key (2026-10)

# ---------------------------------------------------------------- categories
EXPENSE = "Expense"
INCOME = "Income"
TRANSACTION_TYPES = [EXPENSE, INCOME]

EXPENSE_CATEGORIES = ["Food", "Travel", "Shopping", "Health", "Other"]
INCOME_CATEGORIES = ["Pocket Money", "Salary", "Other"]
ALL_CATEGORIES = EXPENSE_CATEGORIES + [
    c for c in INCOME_CATEGORIES if c not in EXPENSE_CATEGORIES
]

# ------------------------------------------------------------ data structure
COLUMNS = ["id", "date", "type", "category", "description", "amount"]

# ---------------------------------------------------------------- validation
MAX_AMOUNT = 10_000_000          # upper limit for a single transaction
MAX_DESCRIPTION_LENGTH = 60

# ------------------------------------------------------------------- budget
BUDGET_WARNING_RATIO = 0.80      # warn when 80% of the monthly budget is used
