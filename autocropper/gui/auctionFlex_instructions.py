import tkinter as tk
from tkinter import ttk


class AuctionFlexInstructionsWindow(tk.Toplevel):
    """
    Post-review instructions window for importing cropped images into AuctionFlex.
    """
    def __init__(self, master, out_dir=None):
        super().__init__(master)
        self.title("AuctionFlex Import Instructions")
        self.geometry("650x500")
        
        # Title
        title_lbl = ttk.Label(
            self,
            text="AuctionFlex Import Instructions",
            font=("Segoe UI", 14, "bold")
        )
        title_lbl.pack(pady=(12, 8), padx=12)
        
        # Separator
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=12, pady=(0, 8))
        
        # Main scrollable text area
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        
        scrollbar = ttk.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        text_widget = tk.Text(
            frame,
            wrap="word",
            yscrollcommand=scrollbar.set,
            font=("Segoe UI", 10),
            padx=8,
            pady=8,
            bg="white",
            relief="sunken",
            bd=1
        )
        scrollbar.config(command=text_widget.yview)
        text_widget.pack(side="left", fill="both", expand=True)
        
        # Build instructions text
        instructions = self._build_instructions_text(out_dir)
        text_widget.insert("1.0", instructions)
        text_widget.config(state="disabled")  # Make read-only
        
        # Bottom button
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=12)
        
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(
            btn_frame,
            text="Copy Output Path",
            command=lambda: self._copy_to_clipboard(out_dir)
        ).pack(side="right", padx=(0, 6))
    
    def _build_instructions_text(self, out_dir: str = None) -> str:
        """Build the full instructions text for AuctionFlex import."""
        instructions = """
AuctionFlex Import Instructions
═══════════════════════════════════════════

Step 1: Locate Your Cropped Images
───────────────────────────────────
Your cropped images are saved in the output folder:
{}

This folder contains all the cropped and reviewed images ready for import.

Step 2: Import the Cropped Images
──────────────────────────────────────
1. Open AuctionFlex on your computer.
2. Select the sale you would like to import images into.
3. Click the Auction Lots & Preview Images button in the Easy Navigator panel.
4. In the Auction Lots window, click the Import Images button in the top right of the window. 
5. Select the output folder from Step 1 when prompted to choose a folder.
6. Ensure the following in the options menu:
    - Assigning Images by: Auction + Lot # is selected and confirm they are assigning to the correct sale
    - Existing Image Mode: Select "Remove Existing Images Prior to Importing New Images"
    - Check the "Smart Auto-Fill" checkbox
7. Check the "Assume filename is lot#/inventory#" box in the Auto-Assign Options menu.
8. Go to the next step and briefly review the image assignments.
9. Complete the import process in the final step.

Step 3: Verify the Import
─────────────────────────
1. Check AuctionFlex to confirm all images are imported correctly
    - Review a few lots to ensure images are properly assigned.
    - Check any lots that may have had corrections, particularly if a lot was split into multiple images or combined.
        - If issues are found, you may need to manually adjust images within AuctionFlex. 

Additional Notes
────────────────
• The program checks for already cropped lots by comparing how many images exist per lot. If corrections were made during review, but the number of images per lot remains the same, those lots may not be re-cropped unless manually adjusted.

Questions or Issues?
──────────────────
If you encounter any problems during the import process, please:
1. Check that all images are in the correct output folder
2. Check that no one is accessing images in the AuctionFlex database during import
3. Double-check the import settings outlined above
4. Make sure no one else is actively using the cropping tool. 
        """.strip()
        
        if out_dir:
            return instructions.format(out_dir)
        else:
            return instructions.format("(No output folder specified)")
    
    def _copy_to_clipboard(self, out_dir: str = None):
        """Copy the output directory path to clipboard."""
        if not out_dir:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(out_dir)
            self.update()  # Now it stays on the clipboard after window closes
        except Exception as e:
            print(f"Failed to copy to clipboard: {e}")
