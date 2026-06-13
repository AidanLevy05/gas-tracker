"""Domain model for a single gas expense.

This module knows nothing about SQLite or the CLI. It just describes what an
expense *is*. Keeping it free of database/UI concerns is what lets the three
layers (model / data access / presentation) stay independent.
"""

from dataclasses import dataclass
from typing import Optional
import sqlite3


@dataclass
class Expense:
    # --- required, user-entered ---
    purchase_date: str          # ISO 8601 string, e.g. "2026-06-13"
    total_price: float          # dollars
    num_gallons: float          # gallons (must be > 0)

    # --- optional / status, with sensible defaults ---
    uploaded_to_concur: bool = False
    reimbursed: bool = False
    receipt_path: Optional[str] = None   # relative path under receipts/
    notes: Optional[str] = None

    # --- set by the database ---
    id: Optional[int] = None
    # price_per_gallon is a *generated* column in SQLite (total_price / num_gallons).
    # We never write it; we only read it back, so it lives here as read-only state.
    price_per_gallon: Optional[float] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Expense":
        """Build an Expense from a sqlite3.Row (with row_factory = sqlite3.Row)."""
        return cls(
            id=row["id"],
            purchase_date=row["purchase_date"],
            total_price=row["total_price"],
            num_gallons=row["num_gallons"],
            price_per_gallon=row["price_per_gallon"],
            uploaded_to_concur=bool(row["uploaded_to_concur"]),
            reimbursed=bool(row["reimbursed"]),
            receipt_path=row["receipt_path"],
            notes=row["notes"],
        )