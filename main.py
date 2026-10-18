"""Start the Expense Tracker.

Run with:   python main.py
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox


def main() -> int:
    # Make the window sharp on high-resolution Windows screens.
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    from storage import ExpenseStore, StorageError

    try:
        store = ExpenseStore()
    except StorageError as exc:
        # The data file is damaged or unreadable: explain instead of crashing.
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Expense Tracker", f"Could not open your data.\n\n{exc}")
        root.destroy()
        return 1

    from gui import ExpenseTrackerApp
    ExpenseTrackerApp(store).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
