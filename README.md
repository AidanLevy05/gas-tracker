# Gas Expense Tracker

A local Python + SQLite tool for tracking gas purchases made during work travel
and their reimbursement lifecycle (uploaded to Concur → reimbursed).

## Run it

```bash
cd gas-tracker
python3 main.py
```

No dependencies beyond the Python standard library (Python 3.10+). The database
(`gas_tracker.db`) and `receipts/` folder are created automatically next to the
scripts on first run.

## Structure

```
gas-tracker/
├── main.py       # CLI / presentation layer (all input + the receipt file copy)
├── database.py   # data access layer (schema + every SQL statement)
├── models.py     # Expense domain model (no SQL, no I/O)
├── receipts/     # receipt images, copied in and named receipt_<id>.jpg
└── gas_tracker.db
```

The three layers don't reach across each other: the CLI calls the `Database`
object, the `Database` returns `Expense` objects, and `models.py` knows nothing
about SQLite or the terminal. Swapping the CLI for a Tkinter GUI later means
touching only `main.py`.

## Design decisions worth knowing

- **`price_per_gallon` is a generated column**, not a stored value you keep in
  sync by hand: `GENERATED ALWAYS AS (total_price / num_gallons) VIRTUAL`. The
  database owns the formula, so the derived value can never drift from its
  inputs — even after an edit. (Verified: editing `total_price` recomputes it.)
- **Booleans are `INTEGER` 0/1 with `CHECK (... IN (0,1))`**, since SQLite has no
  native boolean type. The model converts to/from Python `bool`.
- **A `CHECK (num_gallons > 0)`** both protects the division and rejects bad data
  at the database, not just in the UI.
- **Every query is parameterized** (`?` placeholders) — user input is never
  concatenated into SQL.
- **Receipts live on disk, paths in the DB.** Images are copied into `receipts/`
  named by record id (`receipt_0001.jpg`), and a _relative_ path is stored so the
  project folder stays portable.
- **Aggregates are computed in SQL** (one `SELECT` with `SUM`/`CASE`), and the
  average price/gallon is the weighted figure (total $ ÷ total gallons), which is
  what you actually paid — not a plain mean of the per-fill rates.

## Known tradeoffs

- Money is stored as `REAL`. Fine for a personal tracker; if exact accounting
  ever matters, integer cents avoids floating-point rounding.
- Deleting a record leaves its receipt file on disk on purpose (safer default).

## Possible next steps

CSV export, search/filter by date or status, monthly reports, OCR to pre-fill
values from a receipt photo, and a desktop GUI.
