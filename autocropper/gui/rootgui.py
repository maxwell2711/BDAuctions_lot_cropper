import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ..io_utils import group_images_by_lot, numeric_first_sort, normalize_output_dir
from ..worker import run_cropper
from .review import ReviewController
from .exporter import ExportWindow

class CropperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Cropper")
        self.root.geometry("500x160")

        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()

        root.columnconfigure(1, weight=1)   # make the entry column stretch

        # Row 0: Input
        ttk.Label(root, text="Input Folder:").grid(row=0, column=0, padx=8, pady=(10,2), sticky="w")
        ttk.Entry(root, textvariable=self.input_dir).grid(row=0, column=1, padx=4, pady=(10,2), sticky="ew")
        ttk.Button(root, text="Browse 📂", command=self.select_input_folder).grid(row=0, column=2, padx=8, pady=(10,2))

        # Row 1: Output
        ttk.Label(root, text="Output Folder:").grid(row=1, column=0, padx=8, pady=(30,8), sticky="w")
        ttk.Entry(root, textvariable=self.output_dir).grid(row=1, column=1, padx=4, pady=2, sticky="ew")
        ttk.Button(root, text="Browse 📂", command=self.select_output_folder).grid(row=1, column=2, padx=8, pady=2)

        # Row 2: Actions (single row spanning all columns)
        actions = ttk.Frame(root)
        actions.grid(row=2, column=0, columnspan=3, padx=8, pady=(12,8), sticky="w")
        ttk.Button(actions, text="Run Cropper⮩", command=self.run).pack(side="left", padx=6)
        ttk.Button(actions, text="Export/Change Descriptions 🗊", command=self.skip_to_Export).pack(side="left", padx=6)
        ttk.Button(actions, text="Open Review 🖻", command=self.skip_to_Review).pack(side="left", padx=6)

    # ------- Select input folders
    def select_input_folder(self):
        path = filedialog.askdirectory(title="Select Input Folder")
        if path:
            self.input_dir.set(path)

    def select_output_folder(self):
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_dir.set(path)

    # ------- Helper -------
    # Compute dictionaries of lots in the input and output dir
    # grouped_input / grouped_output are dicts: lot_id(str) -> [paths...]
    def _compute_lots(self, in_dir, out_dir):
        gi = group_images_by_lot(in_dir)
        go = group_images_by_lot(out_dir)
        all_ids = set(gi.keys()) | set(go.keys())
        return gi, go, numeric_first_sort(all_ids)

    def run(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()
        if not os.path.isdir(in_dir) or not os.path.isdir(out_dir):
            messagebox.showerror("Invalid Input", "Please select valid folders.")
            return

        def after_crop():
            # normalize actual filenames on disk
            renamed = normalize_output_dir(out_dir)
            print(f"[normalize] renamed {renamed} files")
            # Recompute mainly for go
            gi, go, lot_list = self._compute_lots(in_dir, out_dir)
            ReviewController(self.root, lot_list, gi, go, self.begin_Export)
            messagebox.showinfo("SUCCESS! Processing Complete", f"Cropped images saved to:\n{out_dir}")

        self.root.withdraw()
        run_cropper(in_dir, out_dir, self.root, after_crop)

    # Callback func for review window
    def begin_Export(self, lot_list):
        # pass the lot list the Export window expects
        ExportWindow(self.root, lot_list)

    def skip_to_Export(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()
        if not os.path.isdir(in_dir) or not os.path.isdir(out_dir):
            messagebox.showerror("Invalid Input", "Please select valid folders.")
            return
        renamed = normalize_output_dir(out_dir)
        print(f"[normalize] renamed {renamed} files")
        # Ensure dicts are up to date 
        gi, go, lot_list = self._compute_lots(in_dir, out_dir)
        self.root.withdraw()
        ExportWindow(self.root, lot_list)

    def skip_to_Review(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()
        if not os.path.isdir(in_dir) or not os.path.isdir(out_dir):
            messagebox.showerror("Invalid Input", "Please select valid folders.")
            return
        renamed = normalize_output_dir(out_dir)
        print(f"[normalize] renamed {renamed} files")
        # Update dicts
        gi, go, lot_list = self._compute_lots(in_dir, out_dir)
        self.root.withdraw()
        ReviewController(self.root, lot_list, gi, go, self.begin_Export)