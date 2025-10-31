import os
import re
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ..io_utils import parse_image_name, group_images_by_lot, compute_export_renames_for_lot, normalize_output_dir

# ---- CSV column map (0-based) ----
LOT_COL              = 0  # col 1
LEAD_COL             = 1  # col 2 (unchanged)
DESC1_COL            = 2  # col 3 (final description goes here)
DESC2_COL            = 3  # col 4
DESC3_COL            = 4  # col 5
DESC4_COL            = 5  # col 6
DESC5_COL            = 6  # col 7
CONSIGNOR_CODE_COL   = 7  # col 8
CONSIGNOR_NAME_COL   = 8  # col 9
# col 10, 11 empty => idx 9, 10
RESERVE_COL          = 11 # col 12
START_BID_COL        = 12 # col 13
IMAGES_START_COL     = 13 # col 14+

_LOTLIKE = re.compile(r"^\s*\d+[A-Za-z]*\s*$")

def _normalize_space(s: str) -> str:
    return " ".join((s or "").split())

def _final_description_from_row(row: list[str]) -> str:
    """Join description columns 3..7 (indices 2..6) into one normalized string."""
    parts = []
    for c in (DESC1_COL, DESC2_COL, DESC3_COL, DESC4_COL, DESC5_COL):
        if c < len(row) and row[c]:
            parts.append(row[c])
    return _normalize_space(" ".join(parts))

class ExportWindow(tk.Toplevel):
    """
    Export/description editor:
      - Write the final description to col 3 (DESC1_COL), clear cols 4..7
      - Update image names in columns 14+ to match on-disk renames
      - Allow appending a uniform snippet with a user-chosen separator
    """
    def __init__(self, master, lot_list, out_dir):
        super().__init__(master)
        self.master = master
        self.out_dir = out_dir
        self.title("Export: Add Descriptions")
        self.minsize(720, 420)

        self.lot_list = set(lot_list)
        self.rows = []
        self.header = None
        self.csv_path = tk.StringVar()
        self.sep = tk.StringVar(value=" ")  # separator between existing desc and new text
        self.preview_var = tk.StringVar(value="No CSV loaded.")
        self.only_session_lots = tk.BooleanVar(value=True)

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(top, text="Export CSV:").pack(side="left")
        ttk.Entry(top, textvariable=self.csv_path, width=60).pack(side="left", padx=6)
        ttk.Button(top, text="Browse…", command=self._choose_csv).pack(side="left")

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

        right = ttk.Frame(mid)
        right.pack(side="left", fill="y", padx=(12, 0))
        ttk.Label(right, text="Preview / Status:").pack(anchor="w")
        self.preview = tk.Listbox(right, height=12, width=36)
        self.preview.pack(fill="y", expand=False, pady=(2, 6))
        ttk.Label(right, textvariable=self.preview_var).pack(anchor="w")

        bot = ttk.Frame(self)
        bot.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(bot, text="Insert default text", command=self._insert_default_text).pack(side="left")
        ttk.Button(bot, text="Apply and Save As…", command=self._apply_and_save).pack(side="right")
        ttk.Button(bot, text="Close", command=self.destroy).pack(side="right", padx=6)

        self.after(0, self._center_and_focus)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _insert_default_text(self):
        dft_txt = (
            "All lots are sold as is, call for full condition report. In person inspection is recommended.\n\n"
            "Shipping disclaimer: Items are marked shipping available. This may be done in house or referred to a third party shipper. "
            "We will contact you after the close of sale if unable to ship in house."
        )
        current = self.txt.get("1.0", "end-1c").strip()
        if dft_txt not in current:
            sep = "\n\n" if current else ""
            self.txt.insert("end-1c", sep + dft_txt)
        self.txt.focus_set()

    def _interpret_escapes(self, s: str) -> str:
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

        # Header detection that works with 6a/10B
        first = rows[0][0].strip() if rows and rows[0] else ""
        self.header = None if _LOTLIKE.match(first) else rows[0]
        self.rows   = rows[1:] if self.header else rows

        # Preview
        self.preview.delete(0, "end")
        sample = self.rows[:50]
        for r in sample:
            lot  = r[LOT_COL] if len(r) > LOT_COL else "(missing)"
            lead = r[LEAD_COL] if len(r) > LEAD_COL else ""
            desc = r[DESC1_COL] if len(r) > DESC1_COL else ""
            clean = desc[:40].replace("\n", " ")
            ell = "…" if len(desc) > 40 else ""
            self.preview.insert("end", f"Lot {lot} | Lead: {lead} | Desc: {clean}{ell}")
        self.preview_var.set(f"Loaded {len(self.rows)} rows.")

    def _get_row_images(self, row: list[str]) -> list[tuple[int, str]]:
        out = []
        for c in range(IMAGES_START_COL, len(row)):
            name = (row[c] or "").strip()
            if name:
                out.append((c, name))
        return out

    def _rewrite_row_images(self, row: list[str], basename_map: dict[str, str]):
        imgs = self._get_row_images(row)
        for col, old in imgs:
            new = basename_map.get(old)
            if new:
                row[col] = new

    def _apply_renames_for_lot(self, lot_id: str) -> dict[str, str]:
        """
        Compute & apply renames on disk for a single lot in self.out_dir.
        Returns {old_basename: new_basename} for updating the CSV row filenames.
        """
        folder = self.out_dir
        # Collect files for this lot
        abs_paths = []
        try:
            for name in os.listdir(folder):
                parsed = parse_image_name(name)
                if not parsed:
                    continue
                lot, _idx, _scheme, _ext = parsed
                if lot.lower() == lot_id.lower():
                    abs_paths.append(os.path.join(folder, name))
        except FileNotFoundError:
            pass

        plan = compute_export_renames_for_lot(abs_paths)
        if not plan:
            return {}

        # Apply plan safely by reusing normalize_output_dir logic
        # (It already does safe renames, but we want only this lot; so mimic locally)
        # We'll do it inline: two-phase move to avoid cycles.
        temps = {}
        used = set(os.listdir(folder))

        def _temp_for(dst_path: str) -> str:
            base = os.path.basename(dst_path)
            stem, ext = os.path.splitext(base)
            k = 0
            while True:
                tmp = f"{stem}.__tmp__{k}{ext}"
                if tmp not in used:
                    used.add(tmp)
                    return os.path.join(folder, tmp)
                k += 1

        for src, dst in plan.items():
            if os.path.exists(src):
                tmp = _temp_for(dst)
                os.replace(src, tmp)
                temps[tmp] = dst

        for tmp, dst in temps.items():
            os.replace(tmp, dst)

        return {os.path.basename(s): os.path.basename(d) for s, d in plan.items()}

    def _apply_and_save(self):
        if not self.rows:
            messagebox.showwarning("Export", "Load a CSV first.")
            return

        snippet = self.txt.get("1.0", "end").strip()
        sep = self._interpret_escapes(self.sep.get())
        allowed_lots = self.lot_list if self.only_session_lots.get() else None

        total_desc_updates = 0
        lot_basename_cache: dict[str, dict[str,str]] = {}

        updated_rows = []
        for r in self.rows:
            if len(r) < IMAGES_START_COL:
                r += [""] * (IMAGES_START_COL - len(r))

            lot_id = (r[LOT_COL].strip() if len(r) > LOT_COL else "")
            if not lot_id:
                updated_rows.append(r)
                continue

            if allowed_lots is not None and lot_id not in allowed_lots:
                updated_rows.append(r)
                continue

            # 1) Build the final description from columns 3..7 (collapse spaces)
            base_desc = _final_description_from_row(r)

            # 2) Append snippet (dedupe by case/space)
            if snippet:
                norm_base = _normalize_space(base_desc).lower()
                norm_snip = _normalize_space(snippet).lower()
                if norm_snip not in norm_base:
                    base_desc = (base_desc + (sep if base_desc and sep else "") + snippet).strip()
                    total_desc_updates += 1

            # 3) Put final description in col 3 and clear cols 4..7
            if len(r) <= DESC1_COL:
                r += [""] * (DESC1_COL - len(r) + 1)
            r[DESC1_COL] = base_desc
            for c in (DESC2_COL, DESC3_COL, DESC4_COL, DESC5_COL):
                if len(r) <= c:
                    r += [""] * (c - len(r) + 1)
                r[c] = ""

            # 4) Ensure on-disk names for this lot match our export policy,
            #    then rewrite row image filenames (cols 14+) to the new basenames.
            if lot_id not in lot_basename_cache:
                lot_basename_cache[lot_id] = self._apply_renames_for_lot(lot_id)
            self._rewrite_row_images(r, lot_basename_cache[lot_id])

            updated_rows.append(r)

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
                w.writerows(updated_rows)
        except Exception as e:
            messagebox.showerror("Export", f"Failed to save:\n{e}")
            return

        messagebox.showinfo(
            "Export",
            f"Updated descriptions for {total_desc_updates} row(s).\nSaved to:\n{out_path}"
        )
        self.destroy()