import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from autocropper.io_utils import group_images_by_lot, numeric_first_sort, normalize_output_dir, compute_already_cropped_lots
from autocropper.worker import run_cropper
from autocropper.gui.review import ReviewController
from autocropper.gui.exporter import ExportWindow

class CropperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Cropper")
        self.root.geometry("500x200")

        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()

        root.columnconfigure(1, weight=1)

        ttk.Label(root, text="Input Folder:").grid(row=0, column=0, padx=8, pady=(10,2), sticky="w")
        ttk.Entry(root, textvariable=self.input_dir).grid(row=0, column=1, padx=4, pady=(10,2), sticky="ew")
        ttk.Button(root, text="Browse 📂", command=self.select_input_folder).grid(row=0, column=2, padx=8, pady=(10,2))

        ttk.Label(root, text="Output Folder (auto):").grid(row=1, column=0, padx=8, pady=(30,8), sticky="w")
        # show auto-generated output folder but disallow manual browse
        out_entry = ttk.Entry(root, textvariable=self.output_dir, state="readonly")
        out_entry.grid(row=1, column=1, padx=4, pady=2, sticky="ew")

        actions = ttk.Frame(root)
        actions.grid(row=3, column=0, columnspan=3, padx=8, pady=(12,8), sticky="w")
        ttk.Button(actions, text="Run Cropper⮩", command=self.run).pack(side="left", padx=6)
        ttk.Button(actions, text="Export/Change Descriptions 🗊", command=self.skip_to_Export).pack(side="left", padx=6)
        ttk.Button(actions, text="Open Review 🖻", command=self.skip_to_Review).pack(side="left", padx=6)

    def _toggle_filter(self):
        """Enable/disable filter folder controls based on checkbox."""
        pass

    def select_input_folder(self):
        path = filedialog.askdirectory(title="Select Input Folder")
        if path:
            self.input_dir.set(path)
            # auto-generate output folder in parent: Cropped_<inputfoldername>
            parent = os.path.dirname(path)
            base = os.path.basename(path)
            out = os.path.join(parent, f"Cropped_{base}")
            try:
                os.makedirs(out, exist_ok=True)
            except Exception:
                pass
            self.output_dir.set(out)

    def select_output_folder(self):
        # Output folder is auto-generated; manual selection disabled.
        messagebox.showinfo("Output Folder", "Output folder is auto-generated from the input folder.")

    def select_filter_folder(self):
        # deprecated: reviewed-file replaces filter folder
        messagebox.showinfo("Reviewed File", "Filtering is now driven by reviewed.txt in the output folder.")

    def _compute_lots(self, in_dir, out_dir):
        gi = group_images_by_lot(in_dir)
        go = group_images_by_lot(out_dir)
        all_ids = set(gi.keys()) | set(go.keys())
        return gi, go, numeric_first_sort(all_ids)

    def _get_skip_lots(self):
        """Compute lots to skip based on reviewed file in the output folder."""
        out_dir = self.output_dir.get()
        if not out_dir or not os.path.isdir(out_dir):
            print("[resume] no output folder yet, skipping resume")
            return set()
        print(f"[resume] using reviewed file in: {out_dir}")
        return compute_already_cropped_lots(self.input_dir.get(), out_dir)

    def run(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()
        if not os.path.isdir(in_dir):
            messagebox.showerror("Invalid Input", "Please select a valid input folder.")
            return
        if not out_dir:
            # generate output if missing
            parent = os.path.dirname(in_dir)
            base = os.path.basename(in_dir)
            out_dir = os.path.join(parent, f"Cropped_{base}")
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception:
                pass
            self.output_dir.set(out_dir)

        # Compute lots to skip based on input/output comparison
        skip_lots = self._get_skip_lots()
        if skip_lots:
            print(f"[resume] skipping lots: {sorted(skip_lots)}")

        def after_crop():
            # normalize output dir filenames
            renamed = normalize_output_dir(out_dir)
            print(f"[normalize] renamed {renamed} files")

            gi, go, lot_list = self._compute_lots(in_dir, out_dir)

            # For review, only show non-skipped lots
            if skip_lots:
                lot_list = [lot for lot in lot_list if lot not in skip_lots]

            if not lot_list:
                messagebox.showinfo("SUCCESS!", "All lots have already been cropped.")
                self.root.deiconify()
                return

            ReviewController(self.root, lot_list, gi, go, self.begin_Export, out_dir=out_dir)
            messagebox.showinfo(
                "SUCCESS! Processing Complete",
                f"Cropped images saved to:\n{out_dir}"
            )

        self.root.withdraw()
        # ensure output folder exists
        try: os.makedirs(out_dir, exist_ok=True)
        except Exception: pass
        run_cropper(in_dir, out_dir, self.root, after_crop, skip_lots=skip_lots)

    def begin_Export(self, lot_list):
        out_dir = self.output_dir.get()
        ExportWindow(self.root, lot_list, out_dir)

    def skip_to_Export(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()
        if not os.path.isdir(in_dir):
            messagebox.showerror("Invalid Input", "Please select valid folders.")
            return
        if not out_dir:
            parent = os.path.dirname(in_dir)
            base = os.path.basename(in_dir)
            out_dir = os.path.join(parent, f"Cropped_{base}")
            try: os.makedirs(out_dir, exist_ok=True)
            except Exception: pass
        renamed = normalize_output_dir(out_dir)
        print(f"[normalize] renamed {renamed} files")
        gi, go, lot_list = self._compute_lots(in_dir, out_dir)
        self.root.withdraw()
        ExportWindow(self.root, lot_list, out_dir)  # pass out_dir

    def skip_to_Review(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()
        if not os.path.isdir(in_dir):
            messagebox.showerror("Invalid Input", "Please select valid folders.")
            return
        if not out_dir:
            parent = os.path.dirname(in_dir)
            base = os.path.basename(in_dir)
            out_dir = os.path.join(parent, f"Cropped_{base}")
            try: os.makedirs(out_dir, exist_ok=True)
            except Exception: pass

        renamed = normalize_output_dir(out_dir)
        print(f"[normalize] renamed {renamed} files")

        gi, go, lot_list = self._compute_lots(in_dir, out_dir)

        # Compute lots to skip based on reviewed file
        skip_lots = self._get_skip_lots()
        if skip_lots:
            lot_list = [lot for lot in lot_list if lot not in skip_lots]
            print(f"[resume] skipping lots: {sorted(skip_lots)}")

        # Check if lot_list is empty after filtering
        if not lot_list:
            messagebox.showinfo("Review", "All lots have already been cropped.")
            return

        self.root.withdraw()
        ReviewController(self.root, lot_list, gi, go, self.begin_Export, out_dir=out_dir)