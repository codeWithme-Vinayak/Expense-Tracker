"""Graphical user interface (Data Input and presentation layer).

The window has three tabs:

  * Transactions - form to add / edit / delete, plus a searchable table
  * Charts       - category pie, monthly trend and daily spending charts
  * Reports      - category and monthly summaries, export to CSV / Excel

Above the tabs, summary cards show income, expenses, savings and the monthly
budget for the month chosen in the drop-down.

This module only deals with what the user sees and clicks. All the real work
(validation, storage, calculations, charts, exports) is done by the other
modules, which keeps this file easy to follow.
"""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, simpledialog, ttk

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import analysis
import charts
import config
import reports
from storage import ExpenseStore, StorageError
from validators import (
    ValidationError,
    validate_budget,
    validate_date,
    validate_transaction,
)

# ------------------------------------------------------------------- styling
BG = "#f4f5f8"
CARD = "#ffffff"
BORDER = "#dcdfe6"
INK = "#0b0b0b"
MUTED = "#52514e"
PRIMARY = "#2a5bd7"
PRIMARY_DARK = "#1f46ab"
GOOD = "#0ca30c"
WARNING = "#fab219"
CRITICAL = "#d03b3b"
INCOME_TEXT = "#4b3bb8"
EXPENSE_TEXT = "#c0332f"

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_CARD = ("Segoe UI", 17, "bold")

ALL_TIME = "All time"
CHART_TYPES = ["Category pie", "Monthly trend", "Daily spending"]


class ExpenseTrackerApp(tk.Tk):
    """The main application window."""

    # ============================================================== set-up
    def __init__(self, store: ExpenseStore | None = None):
        super().__init__()
        self.store = store or ExpenseStore()

        # State that the window remembers between clicks.
        self.selected_id: int | None = None          # row being edited
        self.month_key: str | None = analysis.month_key(date.today())  # None = all time
        self.month_lookup: dict[str, str] = {}       # drop-down label -> "YYYY-MM"
        self.active_filters: dict = {}               # filters applied to the table
        self.sort_column = "date"
        self.sort_descending = True
        self.chart_canvas: FigureCanvasTkAgg | None = None
        self.current_figure = None

        self.title(config.APP_TITLE)
        self.geometry("1180x700")
        self.minsize(1020, 620)
        self.configure(bg=BG)

        self._setup_styles()
        self._build_header()
        self._build_cards()
        self._build_tabs()
        self._build_status_bar()
        self._clear_form()
        self.refresh_all()

    def _setup_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=FONT, background=BG)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
        style.configure("TLabelframe", background=BG, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=BG, foreground=INK, font=FONT_BOLD)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(20, 8), font=FONT_BOLD, background="#e4e7ef")
        style.map("TNotebook.Tab", background=[("selected", CARD)])
        style.configure("Treeview", rowheight=26, font=FONT, background=CARD,
                        fieldbackground=CARD, foreground=INK, bordercolor=BORDER)
        style.configure("Treeview.Heading", font=FONT_BOLD, background="#e9ecf3",
                        foreground=INK, relief="flat", padding=(6, 5))
        style.map("Treeview", background=[("selected", PRIMARY)],
                  foreground=[("selected", "white")])
        style.configure("Primary.TButton", background=PRIMARY, foreground="white",
                        font=FONT_BOLD, padding=(14, 7), borderwidth=0)
        style.map("Primary.TButton",
                  background=[("disabled", "#b7c4f0"), ("active", PRIMARY_DARK)])
        style.configure("TButton", padding=(12, 6), font=FONT)
        for name, colour in (("Ok", GOOD), ("Warning", WARNING), ("Over", CRITICAL)):
            style.configure(f"{name}.Horizontal.TProgressbar", troughcolor="#e6e8ee",
                            background=colour, lightcolor=colour, darkcolor=colour,
                            bordercolor="#e6e8ee")

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(16, 12, 16, 4))
        header.pack(fill="x")
        ttk.Label(header, text=config.APP_TITLE, font=FONT_TITLE).pack(side="left")

        right = ttk.Frame(header)
        right.pack(side="right")
        ttk.Label(right, text="Summary for:").pack(side="left", padx=(0, 6))
        self.month_var = tk.StringVar()
        self.month_box = ttk.Combobox(right, textvariable=self.month_var,
                                      state="readonly", width=18)
        self.month_box.pack(side="left")
        self.month_box.bind("<<ComboboxSelected>>", self._on_month_change)
        ttk.Button(right, text="Set Budget", command=self.on_set_budget).pack(
            side="left", padx=(12, 0))

    def _make_card(self, parent, column: int, title: str, accent: str):
        """A white summary card with a coloured strip on its left edge."""
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=0, column=column, sticky="nsew", padx=6)
        tk.Frame(card, bg=accent, width=5).pack(side="left", fill="y")
        body = tk.Frame(card, bg=CARD, padx=14, pady=10)
        body.pack(side="left", fill="both", expand=True)
        tk.Label(body, text=title, bg=CARD, fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        value = tk.Label(body, text="", bg=CARD, fg=INK, font=FONT_CARD)
        value.pack(anchor="w")
        detail = tk.Label(body, text="", bg=CARD, fg=MUTED, font=FONT_SMALL)
        detail.pack(anchor="w")
        return body, value, detail

    def _build_cards(self) -> None:
        row = ttk.Frame(self, padding=(10, 8, 10, 8))
        row.pack(fill="x")
        for column in range(4):
            row.columnconfigure(column, weight=1, uniform="cards")

        _, self.income_value, self.income_detail = self._make_card(
            row, 0, "Income", charts.INCOME_COLOR)
        _, self.expense_value, self.expense_detail = self._make_card(
            row, 1, "Expenses", charts.EXPENSE_COLOR)
        _, self.savings_value, self.savings_detail = self._make_card(
            row, 2, "Savings (income - expenses)", PRIMARY)
        body, self.budget_value, self.budget_detail = self._make_card(
            row, 3, "Monthly budget", "#8b8a86")
        self.budget_bar = ttk.Progressbar(body, maximum=100, length=200,
                                          style="Ok.Horizontal.TProgressbar")
        self.budget_bar.pack(anchor="w", fill="x", pady=(2, 0))

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(4, 6))
        self._build_transactions_tab()
        self._build_charts_tab()
        self._build_reports_tab()

    def _build_status_bar(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel",
                  padding=(16, 0, 16, 8)).pack(fill="x")

    # ============================================================ tab 1
    def _build_transactions_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Transactions")

        # ---- left: the add / edit form
        form = ttk.LabelFrame(tab, text="Add / edit transaction", padding=14)
        form.pack(side="left", fill="y", padx=(0, 12))

        self.date_var = tk.StringVar()
        self.type_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.desc_var = tk.StringVar()
        self.amount_var = tk.StringVar()

        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        # Row 0-1: date and type
        ttk.Label(form, text="Date (YYYY-MM-DD)").grid(row=0, column=0, sticky="w")
        date_row = ttk.Frame(form)
        date_row.grid(row=1, column=0, sticky="ew", pady=(2, 10), padx=(0, 10))
        date_entry = ttk.Entry(date_row, textvariable=self.date_var, width=11)
        date_entry.pack(side="left")
        ttk.Button(date_row, text="Today", width=6,
                   command=lambda: self.date_var.set(date.today().strftime(config.DATE_FORMAT))
                   ).pack(side="left", padx=(5, 0))

        ttk.Label(form, text="Type").grid(row=0, column=1, sticky="w")
        type_box = ttk.Combobox(form, textvariable=self.type_var, state="readonly",
                                values=config.TRANSACTION_TYPES, width=13)
        type_box.grid(row=1, column=1, sticky="ew", pady=(2, 10))
        type_box.bind("<<ComboboxSelected>>", lambda _e: self._update_category_choices())

        # Row 2-3: category and amount
        ttk.Label(form, text="Category").grid(row=2, column=0, sticky="w")
        self.category_box = ttk.Combobox(form, textvariable=self.category_var,
                                         state="readonly", width=13)
        self.category_box.grid(row=3, column=0, sticky="ew", pady=(2, 10), padx=(0, 10))

        ttk.Label(form, text=f"Amount ({config.CURRENCY})").grid(row=2, column=1, sticky="w")
        self.amount_entry = ttk.Entry(form, textvariable=self.amount_var, width=13)
        self.amount_entry.grid(row=3, column=1, sticky="ew", pady=(2, 10))

        # Row 4-5: description (full width)
        ttk.Label(form, text="Description (optional)").grid(
            row=4, column=0, columnspan=2, sticky="w")
        desc_entry = ttk.Entry(form, textvariable=self.desc_var, width=30)
        desc_entry.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 14))

        # Row 6-8: buttons
        self.add_button = ttk.Button(form, text="Add Transaction", style="Primary.TButton",
                                     command=self.on_add)
        self.add_button.grid(row=6, column=0, columnspan=2, sticky="ew", pady=2)
        self.update_button = ttk.Button(form, text="Save Changes", command=self.on_update)
        self.update_button.grid(row=7, column=0, sticky="ew", pady=2, padx=(0, 4))
        self.delete_button = ttk.Button(form, text="Delete", command=self.on_delete)
        self.delete_button.grid(row=7, column=1, sticky="ew", pady=2, padx=(4, 0))
        ttk.Button(form, text="Clear Form", command=self._clear_form).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Label(form, text="Tip: click a row in the table to edit it.",
                  style="Muted.TLabel", wraplength=280).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # Enter adds (or saves, when a row is selected); Escape clears the form.
        for entry in (date_entry, desc_entry, self.amount_entry):
            entry.bind("<Return>", self._on_form_enter)
            entry.bind("<Escape>", lambda _e: self._clear_form())

        # ---- right: filters and the table
        right = ttk.Frame(tab)
        right.pack(side="left", fill="both", expand=True)

        filters = ttk.LabelFrame(right, text="Search and filter", padding=10)
        filters.pack(fill="x", pady=(0, 8))
        self.filter_from = tk.StringVar()
        self.filter_to = tk.StringVar()
        self.filter_category = tk.StringVar(value="All")
        self.filter_type = tk.StringVar(value="All")
        self.filter_search = tk.StringVar()

        ttk.Label(filters, text="From").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.filter_from, width=11).grid(row=1, column=0, padx=(0, 8))
        ttk.Label(filters, text="To").grid(row=0, column=1, sticky="w")
        ttk.Entry(filters, textvariable=self.filter_to, width=11).grid(row=1, column=1, padx=(0, 8))
        ttk.Label(filters, text="Type").grid(row=0, column=2, sticky="w")
        ttk.Combobox(filters, textvariable=self.filter_type, state="readonly", width=8,
                     values=["All"] + config.TRANSACTION_TYPES).grid(row=1, column=2, padx=(0, 8))
        ttk.Label(filters, text="Category").grid(row=0, column=3, sticky="w")
        ttk.Combobox(filters, textvariable=self.filter_category, state="readonly", width=12,
                     values=["All"] + config.ALL_CATEGORIES).grid(row=1, column=3, padx=(0, 8))
        ttk.Label(filters, text="Search").grid(row=0, column=4, sticky="w")
        search = ttk.Entry(filters, textvariable=self.filter_search, width=15)
        search.grid(row=1, column=4, padx=(0, 8))
        search.bind("<Return>", lambda _e: self.on_apply_filters())
        ttk.Button(filters, text="Apply", style="Primary.TButton",
                   command=self.on_apply_filters).grid(row=1, column=5, padx=(4, 4))
        ttk.Button(filters, text="Reset", command=self.on_reset_filters).grid(row=1, column=6)

        table_frame = ttk.Frame(right)
        table_frame.pack(fill="both", expand=True)
        self.columns = {
            "id": ("ID", 50, "center"),
            "date": ("Date", 100, "center"),
            "type": ("Type", 80, "center"),
            "category": ("Category", 110, "w"),
            "description": ("Description", 260, "w"),
            "amount": (f"Amount ({config.CURRENCY})", 130, "e"),
        }
        self.tree = ttk.Treeview(table_frame, columns=list(self.columns),
                                 show="headings", selectmode="browse")
        for key, (title, width, anchor) in self.columns.items():
            self.tree.heading(key, text=title, command=lambda c=key: self._sort_by(c))
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key == "description"))
        self.tree.tag_configure("income", foreground=INCOME_TEXT)
        self.tree.tag_configure("expense", foreground=INK)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)
        self.tree.bind("<Delete>", lambda _e: self.on_delete())

        self.table_info = ttk.Label(right, text="", style="Muted.TLabel")
        self.table_info.pack(anchor="w", pady=(6, 0))

    # ============================================================ tab 2
    def _build_charts_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Charts")

        controls = ttk.Frame(tab)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="Chart:").pack(side="left", padx=(0, 6))
        self.chart_type_var = tk.StringVar(value=CHART_TYPES[0])
        chart_box = ttk.Combobox(controls, textvariable=self.chart_type_var,
                                 values=CHART_TYPES, state="readonly", width=18)
        chart_box.pack(side="left")
        chart_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_chart())
        ttk.Button(controls, text="Save Chart as Image", command=self.on_save_chart).pack(
            side="left", padx=(12, 0))
        ttk.Label(controls, style="Muted.TLabel",
                  text="The pie and daily charts follow the month chosen at the top; "
                       "the monthly trend always shows every month.").pack(side="left", padx=14)

        self.chart_frame = tk.Frame(tab, bg=charts.SURFACE, highlightbackground=BORDER,
                                    highlightthickness=1)
        self.chart_frame.pack(fill="both", expand=True)

    # ============================================================ tab 3
    def _build_reports_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Reports")

        tables = ttk.Frame(tab)
        tables.pack(fill="both", expand=True)
        tables.columnconfigure(0, weight=1, uniform="reports")
        tables.columnconfigure(1, weight=1, uniform="reports")
        tables.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(tables, text="Spending by category (selected month)", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.category_tree = ttk.Treeview(left, columns=("category", "amount", "share"),
                                          show="headings", height=8)
        for key, title, width, anchor in (("category", "Category", 140, "w"),
                                          ("amount", f"Spent ({config.CURRENCY})", 130, "e"),
                                          ("share", "Share", 80, "e")):
            self.category_tree.heading(key, text=title)
            self.category_tree.column(key, width=width, anchor=anchor)
        self.category_tree.tag_configure("total", font=FONT_BOLD, background="#eef0f6")
        self.category_tree.pack(fill="both", expand=True)

        right = ttk.LabelFrame(tables, text="Month-by-month summary (all months)", padding=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.monthly_tree = ttk.Treeview(right, columns=("month", "income", "expense", "savings"),
                                         show="headings", height=8)
        for key, title, width, anchor in (("month", "Month", 120, "w"),
                                          ("income", "Income", 110, "e"),
                                          ("expense", "Expenses", 110, "e"),
                                          ("savings", "Savings", 110, "e")):
            self.monthly_tree.heading(key, text=title)
            self.monthly_tree.column(key, width=width, anchor=anchor)
        self.monthly_tree.tag_configure("loss", foreground=CRITICAL)
        self.monthly_tree.pack(fill="both", expand=True)

        bottom = ttk.Frame(tab)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Export to CSV", command=self.on_export_csv).pack(side="left")
        ttk.Button(bottom, text="Export to Excel", style="Primary.TButton",
                   command=self.on_export_excel).pack(side="left", padx=8)
        ttk.Label(bottom, style="Muted.TLabel",
                  text="Exports contain the transactions of the month chosen at the top "
                       "(or everything for 'All time').").pack(side="left", padx=8)

    # ========================================================== refreshing
    def refresh_all(self) -> None:
        """Redraw everything from the current data."""
        self._refresh_month_choices()
        self._refresh_cards()
        self._refresh_table()
        self._refresh_chart()
        self._refresh_reports()

    def _month_df(self) -> pd.DataFrame:
        """Transactions of the month chosen at the top (or all of them)."""
        return analysis.filter_transactions(self.store.df, month=self.month_key)

    def _period_label(self) -> str:
        return analysis.month_label(self.month_key) if self.month_key else ALL_TIME

    def _refresh_month_choices(self) -> None:
        months = set(analysis.available_months(self.store.df))
        months.add(analysis.month_key(date.today()))     # always offer this month
        if self.month_key:
            months.add(self.month_key)
        ordered = sorted(months, reverse=True)
        self.month_lookup = {analysis.month_label(m): m for m in ordered}
        self.month_box.configure(values=[ALL_TIME] + list(self.month_lookup))
        self.month_var.set(self._period_label())

    def _refresh_cards(self) -> None:
        fmt = analysis.format_inr
        totals = analysis.totals(self._month_df())
        period = self._period_label()
        self.income_value.configure(text=fmt(totals["income"]))
        self.income_detail.configure(text=period)
        self.expense_value.configure(text=fmt(totals["expense"]))
        self.expense_detail.configure(text=period)

        savings = totals["savings"]
        sign = "+" if savings > 0 else ""
        self.savings_value.configure(text=f"{sign}{fmt(savings)}",
                                     fg=GOOD if savings >= 0 else CRITICAL)
        self.savings_detail.configure(
            text="You are saving money" if savings > 0
            else "Spending equals income" if savings == 0 else "Spending more than income")

        self._refresh_budget_card()

    def _refresh_budget_card(self) -> None:
        fmt = analysis.format_inr
        if self.month_key is None:
            self.budget_value.configure(text="Pick a month", fg=INK)
            self.budget_detail.configure(text="Budgets are tracked month by month")
            self.budget_bar.configure(value=0, style="Ok.Horizontal.TProgressbar")
            return

        status = analysis.budget_status(
            self.store.df, self.month_key, self.store.get_budget(self.month_key))
        if status["status"] == "not_set":
            self.budget_value.configure(text="Not set", fg=INK)
            self.budget_detail.configure(text="Click 'Set Budget' to add one")
            self.budget_bar.configure(value=0, style="Ok.Horizontal.TProgressbar")
            return

        self.budget_value.configure(
            text=f"{fmt(status['spent'], 0)} / {fmt(status['budget'], 0)}",
            fg=CRITICAL if status["status"] == "over" else INK)
        if status["status"] == "over":
            text = f"Over budget by {fmt(-status['remaining'], 0)}"
            style = "Over.Horizontal.TProgressbar"
        elif status["status"] == "warning":
            text = f"Warning: {status['percent']:.0f}% used, {fmt(status['remaining'], 0)} left"
            style = "Warning.Horizontal.TProgressbar"
        else:
            text = f"{status['percent']:.0f}% used, {fmt(status['remaining'], 0)} left"
            style = "Ok.Horizontal.TProgressbar"
        self.budget_detail.configure(text=text)
        self.budget_bar.configure(value=min(status["percent"], 100), style=style)

    def _refresh_table(self) -> None:
        df = analysis.filter_transactions(self.store.df, **self.active_filters)
        df = df.sort_values([self.sort_column, "id"],
                            ascending=[not self.sort_descending] * 2, kind="mergesort")

        self.tree.delete(*self.tree.get_children())
        for row in df.itertuples(index=False):
            tag = "income" if row.type == config.INCOME else "expense"
            self.tree.insert("", "end", iid=str(row.id), tags=(tag,), values=(
                row.id,
                row.date.strftime(config.DATE_FORMAT),
                row.type,
                row.category,
                row.description,
                analysis.format_inr(row.amount),
            ))

        # Show an arrow on the column the table is sorted by.
        for key, (title, _w, _a) in self.columns.items():
            arrow = (" ▼" if self.sort_descending else " ▲") if key == self.sort_column else ""
            self.tree.heading(key, text=title + arrow)

        # Keep the edited row highlighted if it is still visible.
        if self.selected_id is not None:
            if self.tree.exists(str(self.selected_id)):
                self.tree.selection_set(str(self.selected_id))
            else:
                self._clear_form()          # the row is no longer in view

        totals = analysis.totals(df)
        fmt = analysis.format_inr
        self.table_info.configure(
            text=f"{len(df)} record(s) shown   |   Income {fmt(totals['income'])}   |   "
                 f"Expenses {fmt(totals['expense'])}")

    def _refresh_chart(self) -> None:
        kind = self.chart_type_var.get()
        if kind == "Category pie":
            fig = charts.category_pie(self._month_df(), self._period_label())
        elif kind == "Monthly trend":
            fig = charts.monthly_trend(self.store.df)
        else:
            fig = charts.daily_trend(self.store.df, self.month_key)

        if self.chart_canvas is not None:
            self.chart_canvas.get_tk_widget().destroy()
        self.current_figure = fig
        self.chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        self.chart_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.chart_canvas.draw()

    def _refresh_reports(self) -> None:
        fmt = analysis.format_inr
        self.category_tree.delete(*self.category_tree.get_children())
        summary = analysis.category_summary(self._month_df())
        total = float(summary.sum())
        for name, amount in summary.items():
            share = f"{amount / total * 100:.1f}%" if total else "-"
            self.category_tree.insert("", "end", values=(name, fmt(amount), share))
        if total:
            self.category_tree.insert("", "end", tags=("total",),
                                      values=("Total", fmt(total), "100%"))

        self.monthly_tree.delete(*self.monthly_tree.get_children())
        monthly = analysis.monthly_summary(self.store.df).sort_index(ascending=False)
        for month, row in monthly.iterrows():
            tag = ("loss",) if row["Savings"] < 0 else ()
            self.monthly_tree.insert("", "end", tags=tag, values=(
                analysis.month_label(month), fmt(row["Income"]),
                fmt(row["Expense"]), fmt(row["Savings"])))

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    # ============================================================== form
    def _update_category_choices(self) -> None:
        """Show the categories that belong to the chosen type."""
        categories = (config.EXPENSE_CATEGORIES if self.type_var.get() == config.EXPENSE
                      else config.INCOME_CATEGORIES)
        self.category_box.configure(values=categories)
        if self.category_var.get() not in categories:
            self.category_var.set(categories[0])

    def _clear_form(self) -> None:
        self.selected_id = None
        self.date_var.set(date.today().strftime(config.DATE_FORMAT))
        self.type_var.set(config.EXPENSE)
        self._update_category_choices()
        self.category_var.set(config.EXPENSE_CATEGORIES[0])
        self.desc_var.set("")
        self.amount_var.set("")
        if hasattr(self, "tree"):
            self.tree.selection_remove(*self.tree.selection())
        self._set_edit_mode(False)

    def _set_edit_mode(self, editing: bool) -> None:
        """Enable Save/Delete only while an existing row is selected."""
        state = "normal" if editing else "disabled"
        self.update_button.configure(state=state)
        self.delete_button.configure(state=state)
        self.add_button.configure(state="disabled" if editing else "normal")

    def _on_form_enter(self, _event=None) -> None:
        if self.selected_id is None:
            self.on_add()
        else:
            self.on_update()

    def _read_form(self) -> dict | None:
        """Validate the form; show a message and return None if it is wrong."""
        try:
            return validate_transaction(
                self.date_var.get(), self.type_var.get(), self.category_var.get(),
                self.desc_var.get(), self.amount_var.get())
        except ValidationError as exc:
            messagebox.showerror("Please check your input", str(exc), parent=self)
            return None

    def _on_row_select(self, _event=None) -> None:
        """Copy the clicked table row into the form so it can be edited."""
        selection = self.tree.selection()
        if not selection:
            return
        tx_id = int(selection[0])
        try:
            row = self.store.get(tx_id)
        except StorageError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self.selected_id = tx_id
        self.date_var.set(pd.Timestamp(row["date"]).strftime(config.DATE_FORMAT))
        self.type_var.set(row["type"])
        self._update_category_choices()
        self.category_var.set(row["category"])
        self.desc_var.set(row["description"])
        self.amount_var.set(f"{row['amount']:.2f}")
        self._set_edit_mode(True)

    # =========================================================== actions
    def on_add(self) -> None:
        record = self._read_form()
        if record is None:
            return
        try:
            self.store.add(record)
        except StorageError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)
            return
        self._clear_form()
        self.refresh_all()
        self._set_status(f"Added {record['type'].lower()}: "
                         f"{analysis.format_inr(record['amount'])} ({record['category']})")
        self.amount_entry.focus_set()
        self._check_budget(record)

    def on_update(self) -> None:
        if self.selected_id is None:
            return
        record = self._read_form()
        if record is None:
            return
        try:
            self.store.update(self.selected_id, record)
        except StorageError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)
            return
        self._clear_form()
        self.refresh_all()
        self._set_status("Changes saved")
        self._check_budget(record)

    def on_delete(self) -> None:
        if self.selected_id is None:
            return
        try:
            row = self.store.get(self.selected_id)
        except StorageError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        question = (f"Delete this {row['type'].lower()} of "
                    f"{analysis.format_inr(row['amount'])} ({row['category']})?")
        if not messagebox.askyesno("Delete transaction", question, parent=self):
            return
        try:
            self.store.delete(self.selected_id)
        except StorageError as exc:
            messagebox.showerror("Could not delete", str(exc), parent=self)
            return
        self._clear_form()
        self.refresh_all()
        self._set_status("Transaction deleted")

    def _check_budget(self, record: dict) -> None:
        """After saving an expense, warn if the month's budget is nearly or fully used."""
        if record["type"] != config.EXPENSE:
            return
        month = analysis.month_key(record["date"])
        status = analysis.budget_status(self.store.df, month, self.store.get_budget(month))
        fmt = analysis.format_inr
        label = analysis.month_label(month)
        if status["status"] == "over":
            messagebox.showwarning(
                "Budget exceeded",
                f"You have gone over your budget for {label}!\n\n"
                f"Budget:  {fmt(status['budget'])}\n"
                f"Spent:   {fmt(status['spent'])}\n"
                f"Over by: {fmt(-status['remaining'])}", parent=self)
        elif status["status"] == "warning":
            messagebox.showwarning(
                "Budget warning",
                f"You have used {status['percent']:.0f}% of your budget for {label}.\n\n"
                f"Spent: {fmt(status['spent'])} of {fmt(status['budget'])}\n"
                f"Left:  {fmt(status['remaining'])}", parent=self)

    # ---------------------------------------------------- month / budget
    def _on_month_change(self, _event=None) -> None:
        self.month_key = self.month_lookup.get(self.month_var.get())   # None for All time
        self.refresh_all()

    def on_set_budget(self) -> None:
        month = self.month_key
        if month:
            prompt = (f"Budget for {analysis.month_label(month)} (in {config.CURRENCY}).\n"
                      "Enter 0 to remove it.")
        else:
            prompt = (f"Default monthly budget (in {config.CURRENCY}), used for every "
                      "month without its own budget.\nEnter 0 to remove it.")
        current = self.store.get_budget(month)
        text = simpledialog.askstring(
            "Set budget", prompt, parent=self,
            initialvalue=f"{current:.0f}" if current > 0 else "")
        if text is None:
            return
        try:
            amount = validate_budget(text)
            self.store.set_budget(amount, month)
        except (ValidationError, StorageError) as exc:
            messagebox.showerror("Could not set budget", str(exc), parent=self)
            return
        self._refresh_cards()
        self._set_status("Budget updated" if amount else "Budget removed")

    # ---------------------------------------------------------- filters
    def on_apply_filters(self) -> None:
        try:
            start = (validate_date(self.filter_from.get(), allow_future=True)
                     if self.filter_from.get().strip() else None)
            end = (validate_date(self.filter_to.get(), allow_future=True)
                   if self.filter_to.get().strip() else None)
        except ValidationError as exc:
            messagebox.showerror("Invalid filter", str(exc), parent=self)
            return
        if start and end and start > end:
            messagebox.showerror("Invalid filter",
                                 "'From' date must not be after 'To' date.", parent=self)
            return
        self.active_filters = {
            "start": start, "end": end,
            "category": self.filter_category.get(),
            "tx_type": self.filter_type.get(),
            "keyword": self.filter_search.get(),
        }
        self._refresh_table()
        self._set_status("Filters applied")

    def on_reset_filters(self) -> None:
        self.filter_from.set("")
        self.filter_to.set("")
        self.filter_category.set("All")
        self.filter_type.set("All")
        self.filter_search.set("")
        self.active_filters = {}
        self._refresh_table()
        self._set_status("Filters cleared")

    def _sort_by(self, column: str) -> None:
        if column == self.sort_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column, self.sort_descending = column, False
        self._refresh_table()

    # ---------------------------------------------------- charts / export
    def on_save_chart(self) -> None:
        if self.current_figure is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Save chart", defaultextension=".png",
            initialfile=f"chart_{self.chart_type_var.get().lower().replace(' ', '_')}.png",
            filetypes=[("PNG image", "*.png")])
        if not path:
            return
        try:
            self.current_figure.savefig(path, dpi=200,
                                        facecolor=self.current_figure.get_facecolor())
        except OSError as exc:
            messagebox.showerror("Could not save chart", str(exc), parent=self)
            return
        self._set_status(f"Chart saved to {path}")

    def _export(self, kind: str) -> None:
        df = self._month_df()
        if df.empty:
            messagebox.showinfo("Nothing to export",
                                "There are no transactions for this period.", parent=self)
            return
        stem = f"expenses_{self.month_key or 'all_time'}"
        if kind == "csv":
            path = filedialog.asksaveasfilename(
                parent=self, title="Export to CSV", defaultextension=".csv",
                initialfile=f"{stem}.csv", filetypes=[("CSV file", "*.csv")])
            writer = reports.export_csv
        else:
            path = filedialog.asksaveasfilename(
                parent=self, title="Export to Excel", defaultextension=".xlsx",
                initialfile=f"{stem}.xlsx", filetypes=[("Excel workbook", "*.xlsx")])
            writer = reports.export_excel
        if not path:
            return
        try:
            writer(df, path)
        except reports.ExportError as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        self._set_status(f"Exported {len(df)} transaction(s) to {path}")
        messagebox.showinfo("Export complete", f"Saved to:\n{path}", parent=self)

    def on_export_csv(self) -> None:
        self._export("csv")

    def on_export_excel(self) -> None:
        self._export("excel")
