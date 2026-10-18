"""Input validation (Data Input module).

Every value typed by the user passes through these functions before it is
allowed anywhere near the data store. Each function either returns a clean
value or raises ``ValidationError`` with a message that is safe to show
directly to the user.
"""

from __future__ import annotations

import math
from datetime import date, datetime

import config


class ValidationError(ValueError):
    """Raised when user input is not acceptable."""


def validate_amount(text) -> float:
    """Return a positive amount rounded to 2 decimals."""
    cleaned = str(text if text is not None else "")
    cleaned = cleaned.replace(",", "").replace(config.CURRENCY, "").strip()
    if not cleaned:
        raise ValidationError("Amount is required.")
    try:
        value = float(cleaned)
    except ValueError:
        raise ValidationError("Amount must be a number, e.g. 250 or 99.50.") from None
    if not math.isfinite(value):
        raise ValidationError("Amount must be a valid number.")
    if value <= 0:
        raise ValidationError("Amount must be greater than zero.")
    if value > config.MAX_AMOUNT:
        raise ValidationError(
            f"Amount is too large (maximum is {config.CURRENCY}{config.MAX_AMOUNT:,})."
        )
    return round(value, 2)


def validate_date(text, allow_future: bool = False) -> datetime:
    """Return a ``datetime`` parsed from ``YYYY-MM-DD``."""
    text = (text or "").strip()
    if not text:
        raise ValidationError("Date is required (format YYYY-MM-DD).")
    try:
        parsed = datetime.strptime(text, config.DATE_FORMAT)
    except ValueError:
        raise ValidationError(
            "Invalid date. Use the format YYYY-MM-DD, e.g. 2026-10-11."
        ) from None
    if not allow_future and parsed.date() > date.today():
        raise ValidationError("Date cannot be in the future.")
    return parsed


def validate_type(tx_type: str) -> str:
    if tx_type not in config.TRANSACTION_TYPES:
        raise ValidationError("Type must be Expense or Income.")
    return tx_type


def validate_category(category: str, tx_type: str) -> str:
    allowed = (
        config.EXPENSE_CATEGORIES if tx_type == config.EXPENSE
        else config.INCOME_CATEGORIES
    )
    if category not in allowed:
        raise ValidationError(
            f"Please choose a valid category for {tx_type.lower()}: "
            + ", ".join(allowed) + "."
        )
    return category


def validate_description(text) -> str:
    text = " ".join((text or "").split())     # trim and collapse spaces
    if len(text) > config.MAX_DESCRIPTION_LENGTH:
        raise ValidationError(
            f"Description is too long (maximum {config.MAX_DESCRIPTION_LENGTH} characters)."
        )
    return text


def validate_budget(text) -> float:
    """Budget may be 0 (meaning: remove the budget) but not negative."""
    cleaned = str(text if text is not None else "")
    cleaned = cleaned.replace(",", "").replace(config.CURRENCY, "").strip()
    if not cleaned:
        raise ValidationError("Budget amount is required (enter 0 to remove it).")
    try:
        value = float(cleaned)
    except ValueError:
        raise ValidationError("Budget must be a number, e.g. 6000.") from None
    if not math.isfinite(value) or value < 0:
        raise ValidationError("Budget cannot be negative.")
    if value > config.MAX_AMOUNT:
        raise ValidationError("Budget is too large.")
    return round(value, 2)


def validate_transaction(date_text, tx_type, category, description, amount_text) -> dict:
    """Validate a whole form and return a clean record (without an id)."""
    tx_type = validate_type(tx_type)
    return {
        "date": validate_date(date_text),
        "type": tx_type,
        "category": validate_category(category, tx_type),
        "description": validate_description(description),
        "amount": validate_amount(amount_text),
    }
