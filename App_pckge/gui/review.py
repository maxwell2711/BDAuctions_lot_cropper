import os, shutil, tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from ..io_utils import natural_sort_by_index, _order_index  # _order_index used internally for matching
from ..cropper import auto_crop_detected_objects
from .crop_tool import CropTool
from ..runtime import on_root_close

# This controller manages which lot is currently up for review
# and provides the framework for changing the displayed lot
class ReviewController:
    def __init__(self, root, lot_list, grouped_input, grouped_output, on_export_open):
        self.root = root
        self.lot_list = lot_list
        self.gi = grouped_input
        self.go = grouped_output
        self.idx = 0
        self.on_export_open = on_export_open

        lot = self.lot_list[self.idx]
        self.win = LotReviewWindow(
            master=root,
            lot_number=lot,
            before_paths=self.gi.get(lot, []),
            after_paths=self.go.get(lot, []),
            on_prev_lot=self.prev,
            on_next_lot=self.next,
            on_export_open=self.on_export_open,
            lot_list=self.lot_list,
        )

    def open_idx(self, i):
        self.idx = max(0, min(i, len(self.lot_list)-1))
        lot = self.lot_list[self.idx]
        self.win.set_lot(lot, self.gi.get(lot, []), self.go.get(lot, []))

    def prev(self): self.open_idx(self.idx - 1)
    def next(self): self.open_idx(self.idx + 1)

class LotReviewWindow(tk.Toplevel):
    def __init__(self, master, lot_number, before_paths, after_paths,
                 on_prev_lot, on_next_lot, on_export_open, lot_list):
        super().__init__(master)
        self.master = master
        self.title(f"Lot {lot_number} — Review")
        self.lot_number = str(lot_number)
        self.before_paths = natural_sort_by_index(before_paths)
        self.after_paths  = natural_sort_by_index(after_paths)
        self.on_prev_lot = on_prev_lot
        self.on_next_lot = on_next_lot
        self.on_export_open = on_export_open
        self.lot_list = lot_list

        self.THUMB_W, self.THUMB_H = 280, 280
        self.COLS = 3
        self._selected_idx = None
        self._after_labels = []
        self._photo_refs = []

        # Top Toolbar
        self.topbar = ttk.Frame(self)
        self.topbar.pack(fill="x", pady=(8, 4))
        self.header_label = ttk.Label(self.topbar, text=f"Lot {self.lot_number}", font=("Segoe UI", 12, "bold"))
        self.header_label.pack(side="left", padx=(20,0))
        # Top Right Buttons
        ttk.Button(self.topbar, text="⟲ Rotate Left",  command=lambda: self._rotate_selected(-90)).pack(side="right", padx=4)
        ttk.Button(self.topbar, text="⟳ Rotate Right", command=lambda: self._rotate_selected(90)).pack(side="right", padx=4)
        ttk.Button(self.topbar, text="✂ Crop",         command=self._crop_selected).pack(side="right", padx=4)

        # Middle scrollable area
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=6)
        self.canvas = tk.Canvas(mid, highlightthickness=0)
        self.vscroll = ttk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vscroll.grid(row=0, column=1, sticky="ns")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        # The frame holding the content of the grid
        self.content = ttk.Frame(self.canvas)
        self.content_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        # Update scroll region when inner content changes size
        self.content.bind("<Configure>", self._on_content_configure)
        # Resize inner window when content changes width
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Bind Mouse Scrollwheel
        self._bind_mousewheel()

        # Inside Content: Before (left) frame, Button (center) Bar, and After (right) frame
        self.left_frame  = tk.Frame(self.content)
        self.center_bar  = tk.Frame(self.content)
        self.right_frame = tk.Frame(self.content)
        # Create Grids
        self.left_frame.grid(row=0, column=0, sticky="n", padx=(0,10))
        self.center_bar.grid(row=0, column=1, sticky="ns", padx=10)
        self.right_frame.grid(row=0, column=2, sticky="n", padx=(10,0))
        # Add Headers to Before/After frames
        ttk.Label(self.left_frame, text="BEFORE", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))
        ttk.Label(self.right_frame, text="AFTER (click to select, double-click to crop)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))
        # Add Center Bar buttons
        ttk.Button(self.center_bar, text="↩ Revert Selected", width=18, command=self._revert_selected).pack(pady=(350, 6))
        ttk.Button(self.center_bar, text="↩↩ Revert All",     width=18, command=self._revert_all).pack(pady=6)
        ttk.Separator(self.center_bar, orient="horizontal").pack(fill="x", pady=6)
        ttk.Button(self.center_bar, text="♻ Recrop All",      width=18, command=self._recrop_all).pack(pady=6)
        ttk.Button(self.center_bar, text="♻ Recrop Selected", width=18, command=self._recrop_selected).pack(pady=6)

        # Build grids into left/right frames
        self._build_group(self.left_frame,  self.before_paths, selectable=False, is_after=False)
        self._build_group(self.right_frame, self.after_paths,  selectable=True,  is_after=True)

        # Bottom Navigation bar
        self.bot = tk.Frame(self)
        self.bot.pack(fill="x", pady=8)
        ttk.Button(self.bot, text="⟵ Prev Lot", command=self.on_prev_lot).pack(side="left", padx=10)
        ttk.Button(self.bot, text="Next Lot ⟶", command=self.on_next_lot).pack(side="right", padx=10)
        ttk.Button(self.bot, text="Done Review", command=self._done_review).pack(side="right", padx=4)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.minsize(1024, 720)

        self.after(0, self._autosize_to_content)

    def _done_review(self):
        try:
            self.destroy()
        finally:
            # Open export window from callback function
            if callable(self.on_export_open):
                self.on_export_open(self.lot_list)

    def _on_close(self):
        try:
            if self.canvas and self.canvas.winfo_exists():
                self.canvas.unbind("<MouseWheel>")
                self.canvas.unbind("<Button-4>")
                self.canvas.unbind("<Button-5>")
        except Exception:
            pass
        resp = messagebox.askyesnocancel(
            "Finish Review",
            "Would you like to proceed to the Export step?\n\nNo will exit program\nCancel will stay here"
        )
        # Cancel - do nothing
        if resp is None:
            return 
        # Open export window
        if resp is True:
            try: self.destroy()
            finally:
                if callable(self.on_export_open):
                    self.on_export_open(self.lot_list)
        else: # No - close and exit
            try: self.destroy()
            finally:
                on_root_close(self.master)

    # set_lot swaps to a new lot without opening a new window, refreshes data
    def set_lot(self, lot_number, before_paths, after_paths):
        self.lot_number = str(lot_number)
        self.before_paths = natural_sort_by_index(before_paths)
        self.after_paths  = natural_sort_by_index(after_paths)
        self._selected_idx = None

        # Update Lot
        self.title(f"Lot {self.lot_number} — Review")
        self.header_label.configure(text=f"Lot {self.lot_number}")

        # Tear down photo grid frames
        for w in self.left_frame.grid_slaves():
            if int(w.grid_info().get("row", 1)) >= 0:
                w.destroy()
        for w in self.right_frame.grid_slaves():
            if int(w.grid_info().get("row", 1)) >= 0:
                w.destroy()

        # Rebuild before and after frames
        ttk.Label(self.left_frame, text="BEFORE", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))
        ttk.Label(self.right_frame, text="AFTER (click to select, double-click to crop)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))

        self._build_group(self.left_frame,  self.before_paths, selectable=False, is_after=False)
        self._build_group(self.right_frame, self.after_paths,  selectable=True,  is_after=True)
        self.after(0, self._autosize_to_content)
        self._on_content_configure()

    # Resizes window to fit the content and enlarges it to fit most
    # of the screen
    def _autosize_to_content(self):
        # Ensure geometry requests are up to date
        self.update_idletasks()

        # Requested sizes of the inner content (both groups), plus fixed bars
        content_w = self.content.winfo_reqwidth()
        content_h = self.content.winfo_reqheight()
        top_h     = self.topbar.winfo_reqheight()
        bot_h     = self.bot.winfo_reqheight()
        scroll_w  = self.vscroll.winfo_reqwidth() or 16  # typical scrollbar width

        # Screen limits
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        # Add a little padding
        pad_w = 30
        pad_h = 30

        # Desired total window size
        desired_w = content_w + scroll_w + pad_w
        desired_h = top_h + content_h + bot_h + pad_h

        # Clamp to screen (leave margins)
        max_w = int(sw * 0.92)
        max_h = int(sh * 0.92)
        win_w = min(desired_w, max_w)
        win_h = min(desired_h, max_h)

        # Apply sizing
        self.geometry(f"{win_w}x{win_h}")

        # Center the window (slightly above vertical center)
        x = (sw - win_w) // 2
        y = max(0, (sh - win_h) // 3)
        self.geometry(f"{win_w}x{win_h}+{x}+{y}")

        # If content is shorter than the canvas area, expand canvas height to remove extra blank
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

# ----- scroll helpers -----
    def _on_content_configure(self, _evt=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, evt):
        # Make inner frame match canvas width for nice resizing
        canvas_width = evt.width
        self.canvas.itemconfigure(self.content_id, width=canvas_width)

    def _bind_mousewheel(self):
        # Windows/Linux wheel
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        # macOS (older Tk on mac uses Button-4/5)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        # If canvas is gone, just ignore
        if not self.canvas or not self.canvas.winfo_exists():
            return
        try:
            if event.num == 4:        # macOS scroll up
                self.canvas.yview_scroll(-3, "units")
            elif event.num == 5:      # macOS scroll down
                self.canvas.yview_scroll(3, "units")
            else:                      # Windows/Linux
                delta = int(-1 * (event.delta / 120))
                self.canvas.yview_scroll(delta, "units")
        except tk.TclError:
            # Widget destroyed between event and call; ignore
            pass

    # ----- build grids-----
    def _build_group(self, frame, paths, selectable, is_after):
        for w in frame.grid_slaves():
            if int(w.grid_info().get("row", 1)) >= 1:
                w.destroy()
        if is_after:
            self._after_labels.clear()
            # don't clear _photo_refs globally here; keep all refs while window is open

        for i, p in enumerate(paths):
            row = (i // self.COLS) * 2 + 1
            col = (i % self.COLS)

            if os.path.exists(p):
                im = Image.open(p)
                im.thumbnail((self.THUMB_W, self.THUMB_H))
                ph = ImageTk.PhotoImage(im)
                self._photo_refs.append(ph)
                img_label = tk.Label(frame, image=ph, relief="groove", bd=2)
            else:
                img_label = tk.Label(frame, text="(missing)", width=32, height=12, relief="groove")

            if selectable and is_after:
                idx = i
                img_label.bind("<Button-1>", lambda e, k=idx: self._select_after(k))
                img_label.bind("<Double-Button-1>", lambda e, k=idx: self._open_crop_tool(k))

            img_label.grid(row=row, column=col, padx=6, pady=6)

            order_num = _order_index(p, i+1)
            cap = tk.Label(frame, text=f"#{order_num}")
            cap.grid(row=row+1, column=col, pady=(0, 10))

            if is_after:
                self._after_labels.append((img_label, cap))

    # ----- selection & actions -----
    def _select_after(self, idx):
        for j, (lbl, _) in enumerate(self._after_labels):
            lbl.configure(highlightthickness=0)
        self._selected_idx = idx
        sel_lbl, _ = self._after_labels[idx]
        sel_lbl.configure(highlightbackground="#00bfff", highlightcolor="#00bfff", highlightthickness=3)

    def _require_selection(self):
        if self._selected_idx is None:
            messagebox.showinfo("Select", "Select an AFTER image first.")
            return False
        return True

    def _rotate_selected(self, deg):
        if not self._require_selection(): return
        idx = self._selected_idx
        path = self.after_paths[idx]
        if not os.path.exists(path):
            messagebox.showerror("Rotate", "Selected image is missing.")
            return
        try:
            im = Image.open(path)
            im = im.rotate(-deg, expand=True)
            im.save(path)
            self._refresh_after(idx)
        except Exception as e:
            messagebox.showerror("Rotate", str(e))

    def _crop_selected(self):
        if not self._require_selection(): return
        idx = self._selected_idx
        path = self.after_paths[idx]
        if not os.path.exists(path):
            messagebox.showerror("Crop", "Selected image is missing.")
            return

        def on_apply(pil_image):
            try:
                pil_image.save(path)
                self._refresh_after(idx)
            except Exception as e:
                messagebox.showerror("Crop", str(e))

        CropTool(self, path, on_apply)

    def _revert_selected(self):
        if not self._require_selection(): return
        idx = self._selected_idx
        after_p = self.after_paths[idx]
        ord_after = _order_index(after_p, idx+1)
        match_before = None
        for p in self.before_paths:
            if _order_index(p, -1) == ord_after:
                match_before = p
                break
        if match_before is None and idx < len(self.before_paths):
            match_before = self.before_paths[idx]
        if match_before and os.path.exists(match_before):
            shutil.copyfile(match_before, after_p)
            self._refresh_after(idx)
        else:
            messagebox.showerror("Revert", "Matching BEFORE image not found.")

    def _revert_all(self):
        count = 0
        for i in range(len(self.after_paths)):
            after_p = self.after_paths[i]
            ord_after = _order_index(after_p, i+1)
            match_before = None
            for p in self.before_paths:
                if _order_index(p, -1) == ord_after:
                    match_before = p
                    break
            if match_before is None and i < len(self.before_paths):
                match_before = self.before_paths[i]
            if match_before and os.path.exists(match_before):
                shutil.copyfile(match_before, after_p)
                count += 1
        self._rebuild_after()
        messagebox.showinfo("Revert All", f"Reverted {count} images.")

    def _recrop_selected(self):
        if not self._require_selection(): return
        idx = self._selected_idx
        before_p = None
        after_p  = self.after_paths[idx]
        ord_after = _order_index(after_p, idx+1)
        for p in self.before_paths:
            if _order_index(p, -1) == ord_after:
                before_p = p
                break
        if before_p is None and idx < len(self.before_paths):
            before_p = self.before_paths[idx]
        if not (before_p and os.path.exists(before_p)):
            messagebox.showerror("Recrop Selected", "Matching BEFORE image not found.")
            return
        try:
            auto_crop_detected_objects(before_p, after_p)
            self._refresh_after(idx)
        except Exception as e:
            messagebox.showerror("Recrop Selected", str(e))

    def _recrop_all(self):
        count = 0
        for i, after_p in enumerate(self.after_paths):
            before_p = None
            ord_after = _order_index(after_p, i+1)
            for p in self.before_paths:
                if _order_index(p, -1) == ord_after:
                    before_p = p
                    break
            if before_p is None and i < len(self.before_paths):
                before_p = self.before_paths[i]
            if before_p and os.path.exists(before_p):
                try:
                    auto_crop_detected_objects(before_p, after_p)
                    count += 1
                except Exception as e:
                    print("Recrop error:", e)
        self._rebuild_after()
        messagebox.showinfo("Recrop All", f"Recropped {count} images.")

    def _refresh_after(self, idx):
        (lbl, cap) = self._after_labels[idx]
        p = self.after_paths[idx]
        if os.path.exists(p):
            im = Image.open(p)
            im.thumbnail((self.THUMB_W, self.THUMB_H))
            ph = ImageTk.PhotoImage(im)
            self._photo_refs.append(ph)
            lbl.configure(image=ph)
            lbl.image = ph
        else:
            lbl.configure(text="(missing)", image="", width=32, height=12)

    def _rebuild_after(self):
        self._build_group(self.right_frame, self.after_paths, selectable=True, is_after=True)

    def _open_crop_tool(self, idx):
        self._select_after(idx)
        self._crop_selected()