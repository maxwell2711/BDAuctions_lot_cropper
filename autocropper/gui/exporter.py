import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class ExportWindow(tk.Toplevel):
    """
    Add a uniform description snippet to lots in an export CSV.

    CSV assumptions:
      - col 0: lot number
      - col 1: lot lead
      - col 2: lot description  (we append here)
      - cols 7+ image filenames (untouched)
    """
    def __init__(self, master, lot_list):
        super().__init__(master)
        self.master = master
        self.title("Export: Add Descriptions")
        self.minsize(720, 420)

        self.lot_list = set(lot_list)   # lots from your session
        self.rows = []                  # loaded CSV rows
        self.header = None
        self.csv_path = tk.StringVar()
        self.sep = tk.StringVar(value=" ")  # separator between existing desc and new text
        self.preview_var = tk.StringVar(value="No CSV loaded.")
        self.only_session_lots = tk.BooleanVar(value=True)

        # --- Top: choose CSV ---
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(top, text="Export CSV:").pack(side="left")
        ttk.Entry(top, textvariable=self.csv_path, width=60).pack(side="left", padx=6)
        ttk.Button(top, text="Browse…", command=self._choose_csv).pack(side="left")

        # --- Middle: text to append ---
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=12, pady=6)

        left = ttk.Frame(mid)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Text to add to each lot description:").pack(anchor="w")
        self.txt = tk.Text(left, height=8, wrap="word")
        self.txt.pack(fill="both", expand=True, pady=(2, 6))

        opts = ttk.Frame(left)
        opts.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(opts, text="Only apply to lots from this session", variable=self.only_session_lots).pack(anchor="w")
        sep_row = ttk.Frame(opts)
        sep_row.pack(fill="x", pady=(6, 0))
        ttk.Label(sep_row, text="Separator between existing and new text:").pack(side="left")
        ttk.Entry(sep_row, textvariable=self.sep, width=8).pack(side="left", padx=6)
        ttk.Label(sep_row, text="(e.g., space, \\n, or \\r\\n)").pack(side="left")

        # --- Right: preview / stats ---
        right = ttk.Frame(mid)
        right.pack(side="left", fill="y", padx=(12, 0))
        ttk.Label(right, text="Preview / Status:").pack(anchor="w")
        self.preview = tk.Listbox(right, height=12, width=36)
        self.preview.pack(fill="y", expand=False, pady=(2, 6))
        ttk.Label(right, textvariable=self.preview_var).pack(anchor="w")

        # --- Bottom: actions ---
        bot = ttk.Frame(self)
        bot.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(bot, text="Insert default text", command=self._insert_default_text).pack(side="left")
        ttk.Button(bot, text="Apply and Save As…", command=self._apply_and_save).pack(side="right")
        ttk.Button(bot, text="Close", command=self.destroy).pack(side="right", padx=6)

        # if the root is hidden, ensure this window is centered and focused
        self.after(0, self._center_and_focus)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _insert_default_text(self):
        dft_txt = (
            "All lots are sold as is, call for full condition report. In person inspection is recommended.\n\n"
            "Shipping disclaimer: Items are marked shipping available. This may be done in house or referred to a third party shipper. "
            "We will contact you after the close of sale if unable to ship in house."
        )
        current = self.txt.get("1.0", "end-1c").strip()
        # replace current content (or use "end-1c" to append)
        if dft_txt not in current:
            sep = "\n\n" if current else ""
            self.txt.insert("end-1c", sep + dft_txt)
        self.txt.focus_set()

    def _interpret_escapes(self, s: str) -> str:
        # Handle CRLF first, then LF and tab
        return (
            s.replace("\\r\\n", "\r\n")
             .replace("\\n", "\n")
             .replace("\\t", "\t")
        )

    def _center_and_focus(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = max(720, self.winfo_width()), max(420, self.winfo_height())
        x, y = (sw - w) // 2, max(0, (sh - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")
        try: self.focus_force()
        except Exception: pass

    def _choose_csv(self):
        path = filedialog.askopenfilename(
            parent=self, title="Select Export CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        self.csv_path.set(path)
        self._load_csv(path)

    def _load_csv(self, path):
        try:
            with open(path, "r", encoding="cp1252", newline="") as f:
                rdr = csv.reader(f)
                rows = list(rdr)
        except Exception as e:
            messagebox.showerror("CSV", f"Failed to read CSV:\n{e}")
            return

        if not rows:
            messagebox.showerror("CSV", "CSV appears to be empty.")
            return

        # header optional; if you always have a header, keep it. Otherwise detect.
        self.header = rows[0] if not rows[0][0].strip().isdigit() else None
        self.rows = rows[1:] if self.header else rows

        # Populate preview
        self.preview.delete(0, "end")
        sample = self.rows[:50]  # show up to 50 lines in preview
        for r in sample:
            lot = r[0] if len(r) > 0 else "(missing lot)"
            lead = r[1] if len(r) > 1 else ""
            desc = r[2] if len(r) > 2 else ""

            clean = desc[:40].replace("\n", " ")
            ell = "…" if len(desc) > 40 else ""

            self.preview.insert("end", f"Lot {lot} | Lead: {lead} | Desc: {clean}{ell}")
        self.preview_var.set(f"Loaded {len(self.rows)} rows.")

    # Normalize description text for de-dupe: collapse spaces, lowercase
    def _norm(self, s: str) -> str:
        return " ".join((s or "").split()).lower()

    def _apply_and_save(self):
        if not self.rows:
            messagebox.showwarning("Export", "Load a CSV first.")
            return

        snippet = self.txt.get("1.0", "end").strip()
        if not snippet:
            messagebox.showwarning("Export", "Enter text to add or use the default text button.")
            return

        sep = self._interpret_escapes(self.sep.get())
        # Which lots to touch?
        allowed_lots = self.lot_list if self.only_session_lots.get() else None # set of strings

        added = 0
        updated = []
        for r in self.rows:
            # Ensure row has at least 3 columns
            while len(r) < 3:
                r.append("")
            lot = str(r[0]).strip()
            desc_old = r[2] or ""
            # filter by lot set (if enabled)
            if allowed_lots is not None and lot not in allowed_lots:
                updated.append(r); continue
            # de-dupe: if snippet already present (case-insensitive, space-normalized), skip
            if self._norm(snippet) in self._norm(desc_old):
                updated.append(r); continue

            # append with separator; keep existing text
            r[2] = (desc_old + (sep if desc_old and sep else "") + snippet).strip()
            added += 1
            updated.append(r)

        # Ask where to save
        out_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save updated CSV",
            defaultextension=".csv",
            initialfile="export_updated.csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if not out_path:
            return

        try:
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                if self.header:
                    w.writerow(self.header)
                w.writerows(updated)
        except Exception as e:
            messagebox.showerror("Export", f"Failed to save:\n{e}")
            return

        messagebox.showinfo("Export", f"Updated {added} lot descriptions.\nSaved to:\n{out_path}")
        self.destroy()