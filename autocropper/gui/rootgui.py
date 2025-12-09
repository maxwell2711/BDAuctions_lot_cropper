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
        self.filter_dir = tk.StringVar()
        self.use_filter = tk.BooleanVar(value=False)

        root.columnconfigure(1, weight=1)

        ttk.Label(root, text="Input Folder:").grid(row=0, column=0, padx=8, pady=(10,2), sticky="w")
        ttk.Entry(root, textvariable=self.input_dir).grid(row=0, column=1, padx=4, pady=(10,2), sticky="ew")
        ttk.Button(root, text="Browse 📂", command=self.select_input_folder).grid(row=0, column=2, padx=8, pady=(10,2))

        ttk.Label(root, text="Output Folder:").grid(row=1, column=0, padx=8, pady=(30,8), sticky="w")
        ttk.Entry(root, textvariable=self.output_dir).grid(row=1, column=1, padx=4, pady=2, sticky="ew")
        ttk.Button(root, text="Browse 📂", command=self.select_output_folder).grid(row=1, column=2, padx=8, pady=2)

        # Filter folder row
        filter_frame = ttk.Frame(root)
        filter_frame.grid(row=2, column=0, columnspan=3, padx=8, pady=(8,2), sticky="ew")
        self.filter_check = ttk.Checkbutton(filter_frame, text="Filter via folder:", variable=self.use_filter, command=self._toggle_filter)
        self.filter_check.pack(side="left", padx=0)
        self.filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_dir, state="disabled")
        self.filter_entry.pack(side="left", padx=(6,4), fill="x", expand=True)
        self.filter_btn = ttk.Button(filter_frame, text="Browse 📂", command=self.select_filter_folder, state="disabled")
        self.filter_btn.pack(side="left", padx=0)

        actions = ttk.Frame(root)
        actions.grid(row=3, column=0, columnspan=3, padx=8, pady=(12,8), sticky="w")
        ttk.Button(actions, text="Run Cropper⮩", command=self.run).pack(side="left", padx=6)
        ttk.Button(actions, text="Export/Change Descriptions 🗊", command=self.skip_to_Export).pack(side="left", padx=6)
        ttk.Button(actions, text="Open Review 🖻", command=self.skip_to_Review).pack(side="left", padx=6)

    def _toggle_filter(self):
        """Enable/disable filter folder controls based on checkbox."""
        state = "normal" if self.use_filter.get() else "disabled"
        self.filter_entry.configure(state=state)
        self.filter_btn.configure(state=state)

    def select_input_folder(self):
        path = filedialog.askdirectory(title="Select Input Folder")
        if path:
            self.input_dir.set(path)

    def select_output_folder(self):
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_dir.set(path)

    def select_filter_folder(self):
        path = filedialog.askdirectory(title="Select Filter Folder (images to compare against)")
        if path:
            self.filter_dir.set(path)

    def _compute_lots(self, in_dir, out_dir):
        gi = group_images_by_lot(in_dir)
        go = group_images_by_lot(out_dir)
        all_ids = set(gi.keys()) | set(go.keys())
        return gi, go, numeric_first_sort(all_ids)

    def _get_skip_lots(self):
        """Compute lots to skip based on filter settings."""
        if not self.use_filter.get() or not self.filter_dir.get():
            print("[resume] no filter folder set, skipping resume")
            return set()
        
        filter_dir = self.filter_dir.get()
        if not os.path.isdir(filter_dir):
            messagebox.showerror("Invalid Filter", f"Filter folder not found:\n{filter_dir}")
            return set()
        
        print(f"[resume] using filter folder: {filter_dir}")
        return compute_already_cropped_lots(self.input_dir.get(), filter_dir)

    def run(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()
        if not os.path.isdir(in_dir) or not os.path.isdir(out_dir):
            messagebox.showerror("Invalid Input", "Please select valid folders.")
            return

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

            ReviewController(self.root, lot_list, gi, go, self.begin_Export)
            messagebox.showinfo(
                "SUCCESS! Processing Complete",
                f"Cropped images saved to:\n{out_dir}"
            )

        self.root.withdraw()
        run_cropper(in_dir, out_dir, self.root, after_crop, skip_lots=skip_lots)

    def begin_Export(self, lot_list):
        out_dir = self.output_dir.get()
        ExportWindow(self.root, lot_list, out_dir)  # pass out_dir

    def skip_to_Export(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()
        if not os.path.isdir(in_dir) or not os.path.isdir(out_dir):
            messagebox.showerror("Invalid Input", "Please select valid folders.")
            return
        renamed = normalize_output_dir(out_dir)
        print(f"[normalize] renamed {renamed} files")
        gi, go, lot_list = self._compute_lots(in_dir, out_dir)
        self.root.withdraw()
        ExportWindow(self.root, lot_list, out_dir)  # pass out_dir

    def skip_to_Review(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()
        if not os.path.isdir(in_dir) or not os.path.isdir(out_dir):
            messagebox.showerror("Invalid Input", "Please select valid folders.")
            return

        renamed = normalize_output_dir(out_dir)
        print(f"[normalize] renamed {renamed} files")

        gi, go, lot_list = self._compute_lots(in_dir, out_dir)

        # Compute lots to skip based on input/output comparison
        skip_lots = self._get_skip_lots()
        if skip_lots:
            lot_list = [lot for lot in lot_list if lot not in skip_lots]
            print(f"[resume] skipping lots: {sorted(skip_lots)}")

        # Check if lot_list is empty after filtering
        if not lot_list:
            messagebox.showinfo("Review", "All lots have already been cropped.")
            return

        self.root.withdraw()
        ReviewController(self.root, lot_list, gi, go, self.begin_Export)