"""Tkinter desktop GUI for the Gas Expense Tracker.

Replaces the CLI menu in main.py with a windowed interface. Uses the same
Database and Expense objects so all data logic stays in database.py / models.py.
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageTk

from database import Database
from models import Expense

BASE_DIR = Path(__file__).resolve().parent
RECEIPTS_DIR = BASE_DIR / "receipts"
DB_PATH = BASE_DIR / "gas_tracker.db"

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def normalize_receipts_folder():
    """Merge uppercase Receipts/ into lowercase receipts/ if both exist."""
    upper = BASE_DIR / "Receipts"
    lower = BASE_DIR / "receipts"
    if upper.is_dir():
        lower.mkdir(exist_ok=True)
        for f in upper.iterdir():
            dest = lower / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))
        # Remove the uppercase folder if now empty
        try:
            upper.rmdir()
        except OSError:
            pass


def store_receipt(source_path: str, expense_id: int) -> str | None:
    """Copy a receipt image into receipts/ named by expense id; return the
    relative path stored in the database."""
    src = Path(source_path).expanduser()
    if not src.is_file():
        return None
    RECEIPTS_DIR.mkdir(exist_ok=True)
    dest = RECEIPTS_DIR / f"receipt_{expense_id:04d}{src.suffix.lower()}"
    shutil.copy2(src, dest)
    return str(dest.relative_to(BASE_DIR))


class GasTrackerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Gas Expense Tracker")
        self.root.geometry("1100x700")
        self.root.minsize(900, 500)

        normalize_receipts_folder()
        self.db = Database(str(DB_PATH))

        self._receipt_photo = None  # prevent GC of displayed image

        self._build_ui()
        self._refresh_table()

    # ------------------------------------------------------------------ UI setup
    def _build_ui(self):
        # Main paned layout: left = table + buttons, right = receipt preview
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left = ttk.Frame(paned)
        right = ttk.Frame(paned, width=300)
        paned.add(left, weight=3)
        paned.add(right, weight=1)

        # --- Expense table ---
        cols = ("id", "date", "total", "gallons", "ppg",
                "concur", "reimbursed", "receipt")
        self.tree = ttk.Treeview(left, columns=cols, show="headings",
                                 selectmode="browse")

        headers = {
            "id": ("ID", 40),
            "date": ("Date", 90),
            "total": ("Total ($)", 80),
            "gallons": ("Gallons", 70),
            "ppg": ("$/gal", 70),
            "concur": ("Concur", 60),
            "reimbursed": ("Reimbursed", 80),
            "receipt": ("Receipt", 140),
        }
        for col, (text, width) in headers.items():
            self.tree.heading(col, text=text)
            anchor = tk.E if col in ("total", "gallons", "ppg") else tk.W
            self.tree.column(col, width=width, anchor=anchor, minwidth=40)

        scrollbar = ttk.Scrollbar(left, orient=tk.VERTICAL,
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # --- Buttons ---
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        buttons = [
            ("Add Expense", self._add_expense),
            ("Edit Selected", self._edit_expense),
            ("Delete Selected", self._delete_expense),
            ("Toggle Concur", self._toggle_concur),
            ("Toggle Reimbursed", self._toggle_reimbursed),
            ("Summary", self._show_summary),
            ("Refresh", self._refresh_table),
            ("Quit", self.root.quit),
        ]
        for text, cmd in buttons:
            ttk.Button(btn_frame, text=text, command=cmd).pack(
                side=tk.LEFT, padx=3, pady=2)

        # --- Receipt preview ---
        ttk.Label(right, text="Receipt Preview",
                  font=("TkDefaultFont", 11, "bold")).pack(pady=(5, 2))
        self.preview_label = ttk.Label(right, text="No receipt image.",
                                       anchor=tk.CENTER)
        self.preview_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    # ------------------------------------------------------------------ table
    def _refresh_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for e in self.db.get_all_expenses():
            ppg = f"{e.price_per_gallon:.3f}" if e.price_per_gallon else "-"
            receipt = Path(e.receipt_path).name if e.receipt_path else ""
            self.tree.insert("", tk.END, iid=str(e.id), values=(
                e.id,
                e.purchase_date,
                f"{e.total_price:.2f}",
                f"{e.num_gallons:.2f}",
                ppg,
                "Yes" if e.uploaded_to_concur else "No",
                "Yes" if e.reimbursed else "No",
                receipt,
            ))
        self._show_placeholder()

    def _selected_id(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select an expense first.")
            return None
        return int(sel[0])

    # ------------------------------------------------------------------ preview
    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            self._show_placeholder()
            return
        expense = self.db.get_expense(int(sel[0]))
        if not expense or not expense.receipt_path:
            self._show_placeholder()
            return
        img_path = BASE_DIR / expense.receipt_path
        if not img_path.is_file():
            self.preview_label.configure(image="", text="Receipt file not found.")
            self._receipt_photo = None
            return
        self._display_image(img_path)

    def _show_placeholder(self):
        self.preview_label.configure(image="", text="No receipt image.")
        self._receipt_photo = None

    def _display_image(self, path: Path):
        try:
            img = Image.open(path)
        except Exception:
            self.preview_label.configure(image="",
                                         text="Cannot open receipt image.")
            self._receipt_photo = None
            return
        # Fit to preview area preserving aspect ratio
        max_w = max(self.preview_label.winfo_width(), 250)
        max_h = max(self.preview_label.winfo_height(), 350)
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=photo, text="")
        self._receipt_photo = photo  # prevent GC

    # ------------------------------------------------------------------ actions
    def _add_expense(self):
        ExpenseDialog(self.root, self.db, on_save=self._refresh_table)

    def _edit_expense(self):
        eid = self._selected_id()
        if eid is None:
            return
        expense = self.db.get_expense(eid)
        if not expense:
            messagebox.showerror("Error", "Expense not found.")
            return
        ExpenseDialog(self.root, self.db, expense=expense,
                      on_save=self._refresh_table)

    def _delete_expense(self):
        eid = self._selected_id()
        if eid is None:
            return
        expense = self.db.get_expense(eid)
        if not expense:
            return
        if messagebox.askyesno(
                "Delete",
                f"Delete expense #{eid} ({expense.purchase_date}, "
                f"${expense.total_price:.2f})?"):
            self.db.delete_expense(eid)
            self._refresh_table()

    def _toggle_concur(self):
        eid = self._selected_id()
        if eid is None:
            return
        expense = self.db.get_expense(eid)
        if not expense:
            return
        self.db.set_status(eid, uploaded_to_concur=not expense.uploaded_to_concur)
        self._refresh_table()
        self.tree.selection_set(str(eid))

    def _toggle_reimbursed(self):
        eid = self._selected_id()
        if eid is None:
            return
        expense = self.db.get_expense(eid)
        if not expense:
            return
        self.db.set_status(eid, reimbursed=not expense.reimbursed)
        self._refresh_table()
        self.tree.selection_set(str(eid))

    def _show_summary(self):
        s = self.db.summary()
        count = s["count"]
        if count == 0:
            messagebox.showinfo("Summary", "No expenses recorded yet.")
            return
        uploaded = count - s["not_uploaded"]
        reimbursed = count - s["not_reimbursed"]
        msg = (
            f"Total expenses:            {count}\n"
            f"Total spent:               ${s['total_spent']:.2f}\n"
            f"Total gallons:             {s['total_gallons']:.2f}\n"
            f"Avg price/gallon:          ${s['avg_price_per_gallon']:.3f}\n"
            f"\n"
            f"Uploaded to Concur:        {uploaded}\n"
            f"Not uploaded to Concur:    {s['not_uploaded']}\n"
            f"Reimbursed:                {reimbursed}\n"
            f"Not reimbursed:            {s['not_reimbursed']}\n"
            f"Amount awaiting reimb:     ${s['awaiting_amount']:.2f}"
        )
        messagebox.showinfo("Summary", msg)


class ExpenseDialog:
    """Modal dialog for adding or editing an expense."""

    def __init__(self, parent, db: Database, *,
                 expense: Expense | None = None, on_save=None):
        self.db = db
        self.expense = expense
        self.on_save = on_save
        self._receipt_src = None  # path chosen by file picker

        editing = expense is not None
        title = "Edit Expense" if editing else "Add Expense"

        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("400x350")
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        frame = ttk.Frame(self.win, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        row = 0

        def add_field(label_text, default=""):
            nonlocal row
            ttk.Label(frame, text=label_text).grid(
                row=row, column=0, sticky=tk.W, pady=3)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(frame, textvariable=var, width=25)
            entry.grid(row=row, column=1, sticky=tk.W, pady=3, padx=(5, 0))
            row += 1
            return var

        today = datetime.today().strftime("%Y-%m-%d")
        self.date_var = add_field("Date (YYYY-MM-DD):",
                                  expense.purchase_date if editing else today)
        self.price_var = add_field("Total price ($):",
                                   str(expense.total_price) if editing else "")
        self.gallons_var = add_field("Gallons:",
                                     str(expense.num_gallons) if editing else "")

        # Checkboxes
        self.concur_var = tk.BooleanVar(
            value=expense.uploaded_to_concur if editing else False)
        ttk.Checkbutton(frame, text="Uploaded to Concur",
                        variable=self.concur_var).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=3)
        row += 1

        self.reimb_var = tk.BooleanVar(
            value=expense.reimbursed if editing else False)
        ttk.Checkbutton(frame, text="Reimbursed",
                        variable=self.reimb_var).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=3)
        row += 1

        self.notes_var = add_field("Notes:",
                                    expense.notes or "" if editing else "")

        # Receipt picker
        ttk.Label(frame, text="Receipt image:").grid(
            row=row, column=0, sticky=tk.W, pady=3)
        receipt_btn_frame = ttk.Frame(frame)
        receipt_btn_frame.grid(row=row, column=1, sticky=tk.W, pady=3, padx=(5, 0))
        ttk.Button(receipt_btn_frame, text="Choose file…",
                   command=self._pick_receipt).pack(side=tk.LEFT)
        row += 1

        current = ""
        if editing and expense.receipt_path:
            current = Path(expense.receipt_path).name
        self.receipt_label = ttk.Label(
            frame, text=current or "(none)",
            foreground="gray" if not current else "black")
        self.receipt_label.grid(row=row, column=0, columnspan=2,
                                sticky=tk.W, pady=(0, 5))
        row += 1

        # Save / Cancel
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel",
                   command=self.win.destroy).pack(side=tk.LEFT, padx=5)

    def _pick_receipt(self):
        path = filedialog.askopenfilename(
            title="Select receipt image",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.webp"),
                ("All files", "*.*"),
            ])
        if path:
            self._receipt_src = path
            self.receipt_label.configure(
                text=Path(path).name, foreground="black")

    def _save(self):
        # Validate date
        date_str = self.date_var.get().strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid date",
                                 "Enter date as YYYY-MM-DD.", parent=self.win)
            return

        # Validate price
        try:
            price = float(self.price_var.get().strip())
            if price < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid price",
                                 "Total price must be a valid non-negative number.",
                                 parent=self.win)
            return

        # Validate gallons
        try:
            gallons = float(self.gallons_var.get().strip())
            if gallons <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid gallons",
                                 "Gallons must be a positive number.",
                                 parent=self.win)
            return

        notes = self.notes_var.get().strip() or None

        if self.expense:
            # Edit existing
            self.expense.purchase_date = date_str
            self.expense.total_price = price
            self.expense.num_gallons = gallons
            self.expense.uploaded_to_concur = self.concur_var.get()
            self.expense.reimbursed = self.reimb_var.get()
            self.expense.notes = notes

            if self._receipt_src:
                stored = store_receipt(self._receipt_src, self.expense.id)
                if stored:
                    self.expense.receipt_path = stored
                else:
                    messagebox.showwarning("Receipt",
                                           "Could not copy receipt file.",
                                           parent=self.win)

            try:
                self.db.update_expense(self.expense)
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=self.win)
                return
        else:
            # Add new
            exp = Expense(
                purchase_date=date_str,
                total_price=price,
                num_gallons=gallons,
                uploaded_to_concur=self.concur_var.get(),
                reimbursed=self.reimb_var.get(),
                notes=notes,
            )
            try:
                new_id = self.db.add_expense(exp)
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=self.win)
                return

            if self._receipt_src:
                stored = store_receipt(self._receipt_src, new_id)
                if stored:
                    self.db.set_receipt_path(new_id, stored)
                else:
                    messagebox.showwarning("Receipt",
                                           "Could not copy receipt file.",
                                           parent=self.win)

        self.win.destroy()
        if self.on_save:
            self.on_save()


def run():
    root = tk.Tk()
    GasTrackerApp(root)
    root.mainloop()
