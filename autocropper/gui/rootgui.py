import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from autocropper.io_utils import group_images_by_lot, numeric_first_sort, normalize_output_dir, compute_already_cropped_lots, compute_uncropped_lots
from autocropper.worker import run_cropper
from autocropper.gui.review import ReviewController
from autocropper.gui.exporter import ExportWindow

class CropperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Cropper")
        self.root.geometry("500x280")

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

        # Instructions for users (split into parts with button in middle)
        instr_frame = ttk.Frame(root)
        instr_frame.grid(row=2, column=0, columnspan=3, padx=8, pady=(6,0), sticky="ew")
    
        instr_text_1 = "Instructions: Select an input folder. Output folder is auto-generated."
        ttk.Label(instr_frame, text=instr_text_1, wraplength=440, justify="center").pack(anchor="center")
    
        # Button in the middle of instructions
        ttk.Button(instr_frame, text="How to export from AuctionFlex?",
                    command=self._show_auctionFlex_export_help).pack(anchor="center", pady=(6, 6))
    
        instr_text_2 = (
            "Click 'Run Cropper' to process images, then use 'Open Review' to inspect and adjust "
            "results for an export which has been cropped, but not reviewed."
        )
        ttk.Label(instr_frame, text=instr_text_2, wraplength=440, justify="center").pack(anchor="center")

        actions = ttk.Frame(root)
        actions.grid(row=3, column=0, columnspan=3, padx=8, pady=(12,8), sticky="ew")
        ttk.Button(actions, text="Run Cropper⮩", command=self.run).pack(side="left", padx=6)
        # Temporarily disable direct export button; feature does not fit current workflow
        # ttk.Button(actions, text="Export/Change Descriptions 🗊", command=self.skip_to_Export).pack(side="left", padx=6)
        ttk.Button(actions, text="Open Review 🖻", command=self.skip_to_Review).pack(side="right", padx=6)

    def _toggle_filter(self):
        """Enable/disable filter folder controls based on checkbox."""
        pass

    def _show_auctionFlex_export_help(self):
        """Show instructions for exporting cropped images from AuctionFlex."""
        help_text = """
AuctionFlex Export Instructions
════════════════════════════════════════

Step 1: Open AuctionFlex
────────────────────────
Launch AuctionFlex on your computer and select the sale you would like to export into the crop tool.

Step 2: Open Export Window
──────────────────────────────
In AuctionFlex, 
    - Click the Auction Lots & Preview Images button in the Easy Navigator panel.
    - In the Auction Lots window, click the Export button in the bottom left corner of the window

Step 3: Configure Export Settings & Export
────────────────────────
  1. Make sure the Destination folder (the top most section) is correct, generally checking the default box is sufficient.
        - Example output folder: Z:\\auctionflex\AuctionExport_161 or similar.
  2. In image options:
        - In Export What section select "All Images 1_1, 1_2, 1_3".
        - Check "Lot#" in the Image File Name section.
        - Check "Catalog" in the Image Quality section.
  3. Click the Export button to begin exporting images to the specified output folder.

Step 4: Locate Exported Images
────────────────────────────
1. After export is complete, use the crop tool to navigate to the output folder specified in Step 3.
        """
        messagebox.showinfo("AuctionFlex Export Help", help_text)


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

        # For the cropping run we only want to consider what is already present
        # in the output folder (ignore reviewed.txt). For the later review step
        # we will re-evaluate skips including reviewed entries.
        skip_lots_for_crop = compute_already_cropped_lots(in_dir, out_dir, include_reviewed=False)
        if skip_lots_for_crop:
            print(f"[resume] (crop) skipping lots: {sorted(skip_lots_for_crop)}")

        def after_crop():
            # normalize output dir filenames
            renamed = normalize_output_dir(out_dir)
            print(f"[normalize] renamed {renamed} files")

            gi, go, lot_list = self._compute_lots(in_dir, out_dir)

            # For review, re-evaluate skips including reviewed.txt so reviewed
            # entries are honored when showing the review window.
            skip_lots = self._get_skip_lots()
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
        run_cropper(in_dir, out_dir, self.root, after_crop, skip_lots=skip_lots_for_crop)

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