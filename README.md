# Gas Expense Tracker

A desktop Python + SQLite app for tracking gas purchases made during work travel
and their reimbursement lifecycle (uploaded to Concur → reimbursed).

## Run it

```bash
cd gas-tracker
pip install -r req.txt
python main.py
```

**Requirements:**

- Python 3.10+
- Tkinter (included with most Python installations)
- Pillow (installed via `req.txt`)

If Tkinter is missing, install it via your system package manager:

```bash
# Ubuntu/Debian
sudo apt install python3-tk
# Fedora
sudo dnf install python3-tkinter
# macOS
brew install python-tk
```

## What it does

The app opens a desktop window with a table of all gas expenses. You can:

- **Add** a new expense with date, total price, gallons, and an optional receipt image
- **Edit** an existing expense
- **Delete** an expense
- **Toggle Concur upload status** and **reimbursement status** with one click
- **View a summary** of total spending, gallons, average price/gallon, and reimbursement stats
- **Preview receipt images** by selecting an expense in the table

## How receipt images work

- When adding or editing an expense, click **"Choose file…"** to open a file picker
- You do not type image paths manually
- Supported formats: `.jpg`, `.jpeg`, `.png`, `.webp`
- Selected images are **copied** into the `receipts/` folder with a safe name like `receipt_0001.jpg`
- The original file is not modified or moved
- The relative path is stored in the SQLite database
- Receipt previews are shown in the right panel when an expense is selected

## Structure

```
gas-tracker/
├── main.py          # launches the GUI
├── gui.py           # Tkinter GUI (presentation layer)
├── database.py      # data access layer (schema + SQL)
├── models.py        # Expense domain model (no SQL, no UI)
├── receipts/        # receipt images, copied and renamed on import
├── gas_tracker.db   # SQLite database (created automatically)
└── req.txt          # Python dependencies
```

## Database

- Uses **SQLite** (`gas_tracker.db`), created automatically on first run
- `price_per_gallon` is a generated column (`total_price / num_gallons`) — never stored manually
- Booleans are stored as `INTEGER` 0/1 with `CHECK` constraints
- All queries use parameterized placeholders to prevent SQL injection

## Design decisions

- **Three-layer architecture**: `models.py` (domain), `database.py` (data access), `gui.py` (presentation) — each layer is independent
- **Receipts live on disk, paths in the DB.** Images are copied into `receipts/` named by record ID, and a relative path is stored so the project folder stays portable
- **Aggregates computed in SQL** — the average price/gallon is the weighted figure (total $ ÷ total gallons)
