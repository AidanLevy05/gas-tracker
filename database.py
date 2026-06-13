"""Data access layer.

All SQLite interaction lives here. The rest of the app talks to a Database
object and never writes raw SQL. Every query is parameterized (the `?`
placeholders) so user input can never be interpreted as SQL.
"""

import sqlite3
from contextlib import contextmanager
from typing import List, Optional

from models import Expense


SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_date      TEXT    NOT NULL,
    total_price        REAL    NOT NULL CHECK (total_price >= 0),
    num_gallons        REAL    NOT NULL CHECK (num_gallons > 0),

    -- Derived value. We store the *definition*, not a hand-maintained copy,
    -- so it can never drift out of sync with total_price / num_gallons.
    -- VIRTUAL = recomputed on read, takes no disk space.
    price_per_gallon   REAL    GENERATED ALWAYS AS (total_price / num_gallons) VIRTUAL,

    -- SQLite has no native boolean: store 0/1 and constrain the values.
    uploaded_to_concur INTEGER NOT NULL DEFAULT 0 CHECK (uploaded_to_concur IN (0, 1)),
    reimbursed         INTEGER NOT NULL DEFAULT 0 CHECK (reimbursed IN (0, 1)),

    receipt_path       TEXT,
    notes              TEXT
);
"""


class Database:
    def __init__(self, db_path: str = "gas_tracker.db"):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _connect(self):
        """Yield a connection that commits on success and rolls back on error."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row          # rows behave like dicts
        conn.execute("PRAGMA foreign_keys = ON") # good habit even with one table
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ CREATE
    def add_expense(self, expense: Expense) -> int:
        """Insert an expense and return its new id. price_per_gallon is omitted
        because the database generates it."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO expenses
                    (purchase_date, total_price, num_gallons,
                     uploaded_to_concur, reimbursed, receipt_path, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expense.purchase_date,
                    expense.total_price,
                    expense.num_gallons,
                    int(expense.uploaded_to_concur),
                    int(expense.reimbursed),
                    expense.receipt_path,
                    expense.notes,
                ),
            )
            return cur.lastrowid

    # -------------------------------------------------------------------- READ
    def get_all_expenses(self) -> List[Expense]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM expenses ORDER BY purchase_date DESC, id DESC"
            ).fetchall()
        return [Expense.from_row(r) for r in rows]

    def get_expense(self, expense_id: int) -> Optional[Expense]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()
        return Expense.from_row(row) if row else None

    # ------------------------------------------------------------------ UPDATE
    def set_status(
        self,
        expense_id: int,
        *,
        uploaded_to_concur: Optional[bool] = None,
        reimbursed: Optional[bool] = None,
    ) -> None:
        """Update one or both status flags. Only the fields passed are changed."""
        fields, values = [], []
        if uploaded_to_concur is not None:
            fields.append("uploaded_to_concur = ?")
            values.append(int(uploaded_to_concur))
        if reimbursed is not None:
            fields.append("reimbursed = ?")
            values.append(int(reimbursed))
        if not fields:
            return
        values.append(expense_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE expenses SET {', '.join(fields)} WHERE id = ?", values
            )

    def set_receipt_path(self, expense_id: int, receipt_path: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE expenses SET receipt_path = ? WHERE id = ?",
                (receipt_path, expense_id),
            )

    def update_expense(self, expense: Expense) -> None:
        """Full edit of an existing record (everything except generated cols)."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE expenses
                   SET purchase_date = ?, total_price = ?, num_gallons = ?,
                       uploaded_to_concur = ?, reimbursed = ?,
                       receipt_path = ?, notes = ?
                 WHERE id = ?
                """,
                (
                    expense.purchase_date,
                    expense.total_price,
                    expense.num_gallons,
                    int(expense.uploaded_to_concur),
                    int(expense.reimbursed),
                    expense.receipt_path,
                    expense.notes,
                    expense.id,
                ),
            )

    # ------------------------------------------------------------------ DELETE
    def delete_expense(self, expense_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))

    # ----------------------------------------------------------------- SUMMARY
    def summary(self) -> dict:
        """Aggregate the whole table in a single query (let the DB do the math)."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                                                   AS count,
                    COALESCE(SUM(total_price), 0)                              AS total_spent,
                    COALESCE(SUM(num_gallons), 0)                              AS total_gallons,
                    COALESCE(SUM(CASE WHEN uploaded_to_concur = 0 THEN 1 ELSE 0 END), 0) AS not_uploaded,
                    COALESCE(SUM(CASE WHEN reimbursed = 0 THEN 1 ELSE 0 END), 0)         AS not_reimbursed,
                    COALESCE(SUM(CASE WHEN reimbursed = 0 THEN total_price ELSE 0 END), 0) AS awaiting_amount
                FROM expenses
                """
            ).fetchone()

        total_spent = row["total_spent"]
        total_gallons = row["total_gallons"]
        # Weighted average (total $ / total gallons), not a simple mean of the
        # per-fill rates — that's the figure that actually matches what you paid.
        avg_ppg = (total_spent / total_gallons) if total_gallons else 0.0

        return {
            "count": row["count"],
            "total_spent": total_spent,
            "total_gallons": total_gallons,
            "avg_price_per_gallon": avg_ppg,
            "not_uploaded": row["not_uploaded"],
            "not_reimbursed": row["not_reimbursed"],
            "awaiting_amount": row["awaiting_amount"],
        }