"""Safe parsing helpers for values received from HTTP forms/query strings."""
from datetime import datetime
from decimal import Decimal, InvalidOperation


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _parse_int(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_decimal(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return Decimal(str(value).strip())
    except (TypeError, ValueError, InvalidOperation):
        return None


def _parse_float(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
