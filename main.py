"""Command-line interface (presentation layer).

Handles all user interaction and the one piece of filesystem work the app does:
copying a receipt image into receipts/ and recording its path. It talks to the
Database object and never touches SQL directly.
"""

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from database import Database
from models import Expense

BASE_DIR = Path(__file__).resolve().parent
RECEIPTS_DIR = BASE_DIR / "receipts"
DB_PATH = BASE_DIR / "gas_tracker.db"


# --------------------------------------------------------------------- input helpers
def prompt_date(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else " (YYYY-MM-DD)"
    while True:
        raw = input(f"{label}{suffix}: ").strip()
        if not raw and default:
            return default
        try:
            return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            print("  Please enter a valid date like YYYY-MM-DD.")


def prompt_float(label: str, *, minimum: float | None = None,
                 positive: bool = False, default: float | None = None) -> float:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{label}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            value = float(raw)
        except ValueError:
            print("  Please enter a number.")
            continue
        if positive and value <= 0:
            print("  Must be greater than 0.")
            continue
        if minimum is not None and value < minimum:
            print(f"  Must be at least {minimum}.")
            continue
        return value


def prompt_yes_no(label: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} ({d}): ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please answer y or n.")


def prompt_optional(label: str, default: str | None = None) -> str | None:
    suffix = f" [{default}]" if default else " (optional)"
    raw = input(f"{label}{suffix}: ").strip()
    if not raw:
        return default
    return raw


def prompt_int(label: str) -> int | None:
    raw = input(f"{label}: ").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        print("  Not a valid number.")
        return None


# --------------------------------------------------------------------- receipt files
def store_receipt(source_path: str, expense_id: int) -> str | None:
    """Copy a receipt image into receipts/ named by expense id; return the
    relative path stored in the database. Returns None if the source is bad."""
    src = Path(source_path).expanduser()
    if not src.is_file():
        print(f"  No file found at {src} — skipping receipt.")
        return None
    RECEIPTS_DIR.mkdir(exist_ok=True)
    dest = RECEIPTS_DIR / f"receipt_{expense_id:04d}{src.suffix.lower()}"
    shutil.copy2(src, dest)
    return str(dest.relative_to(BASE_DIR))


# --------------------------------------------------------------------- display
def print_expense_row(e: Expense) -> None:
    concur = "yes" if e.uploaded_to_concur else "no "
    reimb = "yes" if e.reimbursed else "no "
    ppg = f"${e.price_per_gallon:.3f}" if e.price_per_gallon is not None else "  -  "
    print(f"  #{e.id:<3} {e.purchase_date}  ${e.total_price:>7.2f}  "
          f"{e.num_gallons:>6.2f} gal  {ppg}/gal  "
          f"concur:{concur}  reimbursed:{reimb}")


def print_expense_detail(e: Expense) -> None:
    print(f"\n  Expense #{e.id}")
    print(f"    Date:             {e.purchase_date}")
    print(f"    Total price:      ${e.total_price:.2f}")
    print(f"    Gallons:          {e.num_gallons:.3f}")
    print(f"    Price/gallon:     ${e.price_per_gallon:.3f}")
    print(f"    Uploaded (Concur):{'yes' if e.uploaded_to_concur else 'no'}")
    print(f"    Reimbursed:       {'yes' if e.reimbursed else 'no'}")
    print(f"    Receipt:          {e.receipt_path or '(none)'}")
    print(f"    Notes:            {e.notes or '(none)'}")


# --------------------------------------------------------------------- actions
def add_expense(db: Database) -> None:
    print("\n-- Add expense --")
    today = datetime.today().strftime("%Y-%m-%d")
    expense = Expense(
        purchase_date=prompt_date("Purchase date", default=today),
        total_price=prompt_float("Total price ($)", minimum=0),
        num_gallons=prompt_float("Gallons", positive=True),
        uploaded_to_concur=prompt_yes_no("Already uploaded to Concur?"),
        reimbursed=prompt_yes_no("Already reimbursed?"),
        notes=prompt_optional("Notes"),
    )
    new_id = db.add_expense(expense)

    receipt = prompt_optional("Path to receipt image")
    if receipt:
        stored = store_receipt(receipt, new_id)
        if stored:
            db.set_receipt_path(new_id, stored)

    saved = db.get_expense(new_id)
    print(f"\n  Saved as #{new_id} "
          f"(price/gallon ${saved.price_per_gallon:.3f}).")


def view_expenses(db: Database) -> None:
    print("\n-- All expenses --")
    expenses = db.get_all_expenses()
    if not expenses:
        print("  (none yet)")
        return
    for e in expenses:
        print_expense_row(e)


def update_status(db: Database) -> None:
    print("\n-- Update status --")
    expense_id = prompt_int("Expense id")
    if expense_id is None:
        return
    e = db.get_expense(expense_id)
    if not e:
        print("  No expense with that id.")
        return
    print_expense_detail(e)
    db.set_status(
        expense_id,
        uploaded_to_concur=prompt_yes_no("Uploaded to Concur?", default=e.uploaded_to_concur),
        reimbursed=prompt_yes_no("Reimbursed?", default=e.reimbursed),
    )
    print("  Updated.")


def edit_expense(db: Database) -> None:
    print("\n-- Edit expense (blank keeps current value) --")
    expense_id = prompt_int("Expense id")
    if expense_id is None:
        return
    e = db.get_expense(expense_id)
    if not e:
        print("  No expense with that id.")
        return
    print_expense_detail(e)

    e.purchase_date = prompt_date("Purchase date", default=e.purchase_date)
    e.total_price = prompt_float("Total price ($)", minimum=0, default=e.total_price)
    e.num_gallons = prompt_float("Gallons", positive=True, default=e.num_gallons)
    e.uploaded_to_concur = prompt_yes_no("Uploaded to Concur?", default=e.uploaded_to_concur)
    e.reimbursed = prompt_yes_no("Reimbursed?", default=e.reimbursed)
    e.notes = prompt_optional("Notes", default=e.notes)

    new_receipt = prompt_optional("Replace receipt image? path")
    if new_receipt:
        stored = store_receipt(new_receipt, e.id)
        if stored:
            e.receipt_path = stored

    db.update_expense(e)
    print("  Updated.")


def delete_expense(db: Database) -> None:
    print("\n-- Delete expense --")
    expense_id = prompt_int("Expense id")
    if expense_id is None:
        return
    e = db.get_expense(expense_id)
    if not e:
        print("  No expense with that id.")
        return
    print_expense_detail(e)
    if prompt_yes_no("Delete this record?"):
        db.delete_expense(expense_id)
        print("  Deleted. (Receipt file left on disk.)")
    else:
        print("  Cancelled.")


def show_summary(db: Database) -> None:
    s = db.summary()
    print("\n-- Summary --")
    print(f"  Expenses recorded:        {s['count']}")
    print(f"  Total spent on gas:       ${s['total_spent']:.2f}")
    print(f"  Total gallons:            {s['total_gallons']:.2f}")
    print(f"  Avg price/gallon:         ${s['avg_price_per_gallon']:.3f}")
    print(f"  Not uploaded to Concur:   {s['not_uploaded']}")
    print(f"  Awaiting reimbursement:   {s['not_reimbursed']}")
    print(f"  $ awaiting reimbursement: ${s['awaiting_amount']:.2f}")


# --------------------------------------------------------------------- menu loop
MENU = """
=== Gas Expense Tracker ===
  1) Add expense
  2) View expenses
  3) Update Concur / reimbursement status
  4) Edit an expense
  5) Delete an expense
  6) Summary
  0) Quit
"""


def clear_screen() -> None:
    """Clear the terminal. Uses the OS command on a real terminal; falls back to
    blank lines when output isn't a TTY (e.g. piped input) so nothing breaks."""
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")
    else:
        print("\n" * 3)


def main() -> None:
    db = Database(str(DB_PATH))
    actions = {
        "1": add_expense,
        "2": view_expenses,
        "3": update_status,
        "4": edit_expense,
        "5": delete_expense,
        "6": show_summary,
    }
    while True:
        clear_screen()
        print(MENU)
        choice = input("Choose: ").strip()
        if choice in ("0", "q", "quit", "exit"):
            print("Bye.")
            break
        action = actions.get(choice)
        if action:
            try:
                action(db)
            except Exception as exc:  # keep the app alive on bad input/IO
                print(f"  Error: {exc}")
        else:
            print("  Unknown choice.")
        # Pause so the result stays on screen until you're ready to move on;
        # the next loop clears it and redraws the menu.
        input("\nPress Enter to continue...")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nBye.")
        sys.exit(0)