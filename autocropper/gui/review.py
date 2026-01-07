import os, shutil, tkinter as tk
import gc
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from autocropper.io_utils import sort_paths_by_index, display_order_for_path, parse_image_name, _target_name, _apply_renames
from autocropper.cropper import auto_crop_detected_objects
from autocropper.gui.crop_tool import CropTool
from autocropper.gui.auctionFlex_instructions import AuctionFlexInstructionsWindow
from autocropper.runtime import on_root_close


# Lightweight tooltip helper for hover hints
class Tooltip:
    def __init__(self, widget, text, wait=400):
        self.widget = widget
        self.text = text
        self.wait = wait
        self.tipwin = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<Motion>", self._motion)

    def _schedule(self, _e=None):
        self._after_id = self.widget.after(self.wait, self._show)

    def _show(self):
        if self.tipwin:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tipwin = tk.Toplevel(self.widget)
        self.tipwin.wm_overrideredirect(True)
        lbl = tk.Label(self.tipwin, text=self.text, justify="left",
                       background="#ffffe0", relief="solid", borderwidth=1,
                       padx=6, pady=3)
        lbl.pack()
        try:
            self.tipwin.wm_geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _hide(self, _e=None):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self.tipwin:
            try:
                self.tipwin.destroy()
            except Exception:
                pass
            self.tipwin = None

    def _motion(self, _e=None):
        # keep tooltip scheduled while moving over widget
        return

class ReviewController:
    def __init__(self, root, lot_list, grouped_input, grouped_output, on_export_open, out_dir=None):
        self.root = root
        self.lot_list = lot_list
        self.gi = grouped_input
        self.go = grouped_output
        self.idx = 0
        self.on_export_open = on_export_open
        self.out_dir = out_dir

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
            grouped_input=self.gi,
            grouped_output=self.go,
            out_dir=self.out_dir,
        )

    def open_idx(self, i):
        self.idx = max(0, min(i, len(self.lot_list)-1))
        lot = self.lot_list[self.idx]
        self.win.set_lot(lot, self.gi.get(lot, []), self.go.get(lot, []))

    def prev(self): self.open_idx(self.idx - 1)
    def next(self): self.open_idx(self.idx + 1)

class LotReviewWindow(tk.Toplevel):
    def __init__(self, master, lot_number, before_paths, after_paths,
                 on_prev_lot, on_next_lot, on_export_open, lot_list,
                 grouped_input=None, grouped_output=None, out_dir=None):
        super().__init__(master)
        self.master = master
        self.title(f"Lot {lot_number} — Review")
        self.lot_number = str(lot_number)
        self.before_paths = sort_paths_by_index(before_paths)
        self.after_paths  = sort_paths_by_index(after_paths)
        # store full maps so we can save across all lots on close
        self.gi = grouped_input or {}
        self.go = grouped_output or {}
        self.out_dir = out_dir
        self.on_prev_lot = on_prev_lot
        self.on_next_lot = on_next_lot
        self.on_export_open = on_export_open
        self.lot_list = lot_list

        self.THUMB_W, self.THUMB_H = 280, 280
        self.COLS = 3
        self._resize_job = None
        self._selected_idx = None
        self._after_labels = []

        # Top Toolbar
        self.topbar = ttk.Frame(self)
        self.topbar.pack(fill="x", pady=(8, 4))
        self.header_label = ttk.Label(self.topbar, text=f"Lot {self.lot_number}", font=("Segoe UI", 12, "bold"))
        self.header_label.pack(side="left", padx=(20,0))
        # --- Jump to lot controls (top-left) ---
        jump_box = ttk.Frame(self.topbar)
        jump_box.pack(side="left", padx=(12, 0))

        ttk.Label(jump_box, text="Jump to lot:").pack(side="left", padx=(6, 4))
        self._jump_var = tk.StringVar()
        ent = ttk.Entry(jump_box, textvariable=self._jump_var, width=10)
        ent.pack(side="left")
        ent.bind("<Return>", lambda e: self._jump_to_lot())
        ent.bind("<FocusIn>", lambda e: self._unbind_hotkeys())
        ent.bind("<FocusOut>", lambda e: self._bind_hotkeys())

        go_btn = ttk.Button(jump_box, text="Go", command=self._jump_to_lot)
        go_btn.pack(side="left", padx=(4, 0))
        Tooltip(go_btn, "Go to the entered lot number, click to focus typing (hotkey: Enter)")

        rotate_l_btn = ttk.Button(self.topbar, text="⟲ Rotate Left",  command=lambda: self._rotate_selected(-90))
        rotate_l_btn.pack(side="right", padx=4)
        Tooltip(rotate_l_btn, "Rotate selected image left (hotkey: 4 or Left arrow)")

        rotate_r_btn = ttk.Button(self.topbar, text="⟳ Rotate Right", command=lambda: self._rotate_selected(90))
        rotate_r_btn.pack(side="right", padx=4)
        Tooltip(rotate_r_btn, "Rotate selected image right (hotkey: 6 or Right arrow)")

        crop_btn = ttk.Button(self.topbar, text="✂ Crop",         command=self._crop_selected)
        crop_btn.pack(side="right", padx=4)
        Tooltip(crop_btn, "Open crop tool for selected image (hotkey: C or 5; double-click image to open)")

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

        self.content = ttk.Frame(self.canvas)
        self.content_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.content.bind("<Configure>", self._on_content_configure)
        


        # Inside Content: Left (before), Center (actions), Right (after)
        self.left_frame  = tk.Frame(self.content)
        self.center_bar  = tk.Frame(self.content)
        self.right_frame = tk.Frame(self.content)
        self.left_frame.grid(row=0, column=0, sticky="n", padx=(0,10))
        self.center_bar.grid(row=0, column=1, sticky="ns", padx=10)
        self.right_frame.grid(row=0, column=2, sticky="n", padx=(10,0))

        ttk.Label(self.left_frame, text="BEFORE", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))
        ttk.Label(self.right_frame, text="AFTER (click to select, double-click to crop)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))

        revert_sel_btn = ttk.Button(self.center_bar, text="↩ Revert Selected", width=18, command=self._revert_selected)
        revert_sel_btn.pack(pady=(300, 6))
        Tooltip(revert_sel_btn, "Revert the selected AFTER image to the original BEFORE image (hotkey: R or 3)")

        revert_all_btn = ttk.Button(self.center_bar, text="↩↩ Revert All",     width=18, command=self._revert_all)
        revert_all_btn.pack(pady=6)
        Tooltip(revert_all_btn, "Revert all AFTER images in this lot to their BEFORE sources (no hotkey assigned)")

        ttk.Separator(self.center_bar, orient="horizontal").pack(fill="x", pady=6)

        recrop_all_btn = ttk.Button(self.center_bar, text="♻ Recrop All",      width=18, command=self._recrop_all)
        recrop_all_btn.pack(pady=6)
        Tooltip(recrop_all_btn, "Re-run auto-cropping on all AFTER images for this lot (no hotkey assigned)")

        recrop_sel_btn = ttk.Button(self.center_bar, text="♻ Recrop Selected", width=18, command=self._recrop_selected)
        recrop_sel_btn.pack(pady=6)
        Tooltip(recrop_sel_btn, "Re-run auto-cropping on the selected image (no hotkey assigned)")

        ttk.Separator(self.center_bar, orient="horizontal").pack(fill="x", pady=6)

        delete_sel_btn = ttk.Button(self.center_bar, text="🗑 Delete Selected", width=18, command=self._delete_selected)
        delete_sel_btn.pack(pady=6)
        Tooltip(delete_sel_btn, "Delete the selected AFTER image and mark it reviewed (no hotkey assigned)")

        self._build_group(self.left_frame,  self.before_paths, selectable=False, is_after=False)
        self._build_group(self.right_frame, self.after_paths,  selectable=True,  is_after=True)

        self._enable_global_scroll()

        # Bottom nav
        self.bot = tk.Frame(self)
        self.bot.pack(fill="x", pady=8)
        next_btn = ttk.Button(self.bot, text="Next Lot ⟶", command=self._mark_and_next)
        next_btn.pack(side="right", padx=10)
        Tooltip(next_btn, "Mark this lot reviewed and go to the next lot (hotkey: N)")

        prev_btn = ttk.Button(self.bot, text="⟵ Prev Lot", command=self._mark_and_prev)
        prev_btn.pack(side="right", padx=4)
        Tooltip(prev_btn, "Mark this lot reviewed and go to the previous lot (hotkey: P)")

        done_btn = ttk.Button(self.bot, text="Done Review", command=self._done_review)
        done_btn.pack(side="right", padx=4)
        Tooltip(done_btn, "Finish reviewing and return to the main window (no hotkey assigned)")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.minsize(1024, 720)
        self.after(0, self._autosize_to_content)

        # Hotkey bindings (stored so we can unbind when jump-entry has focus)
        self._hotkey_bindings = [
            ("<Left>",  lambda e: self._rotate_selected(-90)),
            ("<KP_Left>",  lambda e: self._rotate_selected(-90)),
            ("<KP_4>",  lambda e: self._rotate_selected(-90)),
            ("4",  lambda e: self._rotate_selected(-90)),
            ("<Right>", lambda e: self._rotate_selected(90)),
            ("<KP_Right>", lambda e: self._rotate_selected(90)),
            ("<KP_6>", lambda e: self._rotate_selected(90)),
            ("6", lambda e: self._rotate_selected(90)),
            ("<Up>", lambda e: self._selected_image_index(1)),
            ("<KP_Up>", lambda e: self._selected_image_index(1)),
            ("<KP_8>", lambda e: self._selected_image_index(1)),
            ("8", lambda e: self._selected_image_index(1)),
            ("<Down>", lambda e: self._selected_image_index(-1)),
            ("<KP_Down>", lambda e: self._selected_image_index(-1)),
            ("<KP_2>", lambda e: self._selected_image_index(-1)),
            ("2", lambda e: self._selected_image_index(-1)),
            ("<R>", lambda e: self._revert_selected()),
            ("<r>", lambda e: self._revert_selected()),
            ("<KP_3>", lambda e: self._revert_selected()),
            ("3", lambda e: self._revert_selected()),
            ("<KP_Next>", lambda e: self._revert_selected()),
            ("<N>", lambda e: self._mark_and_next()),
            ("<n>", lambda e: self._mark_and_next()),
            ("<KP_Prior>", lambda e: self._mark_and_next()),
            ("<KP_9>", lambda e: self._mark_and_next()),
            ("9", lambda e: self._mark_and_next()),
            ("<P>", lambda e: self._mark_and_prev()),
            ("<p>", lambda e: self._mark_and_prev()),
            ("<KP_Home>", lambda e: self._mark_and_prev()),
            ("<KP_7>", lambda e: self._mark_and_prev()),
            ("7", lambda e: self._mark_and_prev()),
            ("<C>", lambda e: self._crop_selected()),
            ("<c>", lambda e: self._crop_selected()),
            ("<KP_5>", lambda e: self._crop_selected()),
            ("5", lambda e: self._crop_selected()),
        ]
        self._bind_hotkeys()
        self.focus_force()

    def _bind_hotkeys(self):
        for seq, handler in getattr(self, "_hotkey_bindings", []):
            try:
                self.bind(seq, handler)
            except Exception:
                pass

    def _unbind_hotkeys(self):
        for seq, _ in getattr(self, "_hotkey_bindings", []):
            try:
                self.unbind(seq)
            except Exception:
                pass

    def _done_review(self):
        save_resp = messagebox.askyesno(
                "Save Copy?",
                "Would you like to mark the current lot as reviewed?"
        )
        
        if save_resp is None or save_resp is False:
            self._disable_global_scroll()
            self._clear_image_refs(self.left_frame)
            self._clear_image_refs(self.right_frame)
            try:
                self.destroy()
            finally:
                # Return to main/root window (do not open Export for now)
                try:
                    self.master.deiconify()
                except Exception:
                    pass
                # Show AuctionFlex import instructions
                try:
                    AuctionFlexInstructionsWindow(self.master, out_dir=self.out_dir)
                except Exception as e:
                    print(f"Failed to open AuctionFlex instructions: {e}")
            return
        if save_resp:
            self._mark_current_lot_reviewed()
        try:
            self.destroy()
        finally:
            # Return to main/root window (do not open Export for now)
            try:
                self.master.deiconify()
            except Exception:
                pass
            # Show AuctionFlex import instructions
            try:
                AuctionFlexInstructionsWindow(self.master, out_dir=self.out_dir)
            except Exception as e:
                print(f"Failed to open AuctionFlex instructions: {e}")

    def _rotate_index(self, idx: int, deg: int):
        # select, then rotate; keeps UI consistent with highlight
        self._select_after(idx)
        self._rotate_selected(deg)

    def _jump_to_lot(self):
        target = (self._jump_var.get() or "").strip()
        if not target:
            return
        # Exact match on lot id as keyed in visible lot_list (supports '6', '6a', etc.)
        idx = None
        try:
            idx = self.lot_list.index(target)
        except ValueError:
            # fallback: case-insensitive match within visible list
            lowered = [s.lower() for s in self.lot_list]
            if target.lower() in lowered:
                idx = lowered.index(target.lower())
            else:
                # not in visible list: try to find in full input groups (allows jumping to already-reviewed lots)
                all_keys = list(self.gi.keys())
                lowered_all = [s.lower() for s in all_keys]
                if target.lower() in lowered_all:
                    lot = all_keys[lowered_all.index(target.lower())]
                    # show that lot locally
                    self.master.after(0, lambda: self.master.focus_force())
                    self._jump_var.set("")
                    self.set_lot(lot, self.gi.get(lot, []), self.go.get(lot, []))
                    return
                messagebox.showinfo("Jump", f"Lot '{target}' not found.")
                return
        # swap to that lot
        self.master.after(0, lambda: self.master.focus_force())  # keep app focused
        self._jump_var.set("")  # clear box
        # Ask controller to open it if available, else set here (works if controller unavailable)
        try:
            # common path: window was created by ReviewController
            # find our controller via a bound method on prev/next (optional)
            self.on_prev_lot.__self__.open_idx(idx)  # type: ignore[attr-defined]
        except Exception:
            # fallback: do it locally if we can't reach controller
            lot = self.lot_list[idx]
            self.set_lot(lot, self.gi.get(lot, []), self.go.get(lot, []))  # needs gi/go if stored

    def _on_close(self):
        # Simplified close: ask to save copy, then return to main window.
        resp = messagebox.askyesnocancel(
            "Finish Review",
            "Would you like to mark the current lot as reviewed? Cancel to stay."
        )
        if resp is None:
            return

        if resp:
            self._mark_current_lot_reviewed()

        self._disable_global_scroll()
        self._clear_image_refs(self.left_frame)
        self._clear_image_refs(self.right_frame)
        try:
            self.destroy()
        finally:
            try:
                self.master.deiconify()
            except Exception:
                pass
            # Show AuctionFlex import instructions after review is done
            try:
                AuctionFlexInstructionsWindow(self.master, out_dir=self.out_dir)
            except Exception as e:
                print(f"Failed to open AuctionFlex instructions: {e}")


    def _copy_reviewed_images(self, dest_folder):
        """Copy all AFTER images for the review session into a single folder.

        Filenames are kept as-is. If a file with the same name already exists in
        the destination it will be skipped (no renaming/overwriting).
        """
        try:
            os.makedirs(dest_folder, exist_ok=True)

            total_copied = 0

            # Iterate every lot in the current review session and copy its AFTER images
            for lot in self.lot_list:
                after_paths = sort_paths_by_index(self.go.get(lot, []))
                for src in after_paths:
                    if not os.path.exists(src):
                        continue
                    base = os.path.basename(src)
                    dest_path = os.path.join(dest_folder, base)


                    shutil.copy2(src, dest_path)
                    total_copied += 1

            messagebox.showinfo(
                "Save Complete",
                f"Copied {total_copied} images."
            )
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to copy images:\n{e}")

    def set_lot(self, lot_number, before_paths, after_paths):
        self.lot_number = str(lot_number)
        self.before_paths = sort_paths_by_index(before_paths)
        self.after_paths  = sort_paths_by_index(after_paths)
        self._selected_idx = None

        self.title(f"Lot {self.lot_number} — Review")
        self.header_label.configure(text=f"Lot {self.lot_number}")

        self._clear_image_refs(self.left_frame)
        self._clear_image_refs(self.right_frame)
        for w in self.left_frame.grid_slaves():
            if int(w.grid_info().get("row", 1)) >= 0:
                w.destroy()
        for w in self.right_frame.grid_slaves():
            if int(w.grid_info().get("row", 1)) >= 0:
                w.destroy()

        ttk.Label(self.left_frame, text="BEFORE", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))
        ttk.Label(self.right_frame, text="AFTER (click to select, double-click to crop)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))

        self._build_group(self.left_frame,  self.before_paths, selectable=False, is_after=False)
        self._build_group(self.right_frame, self.after_paths,  selectable=True,  is_after=True)
        self.after(0, self._autosize_to_content)
        self._on_content_configure()

    def _autosize_to_content(self):
        self.update_idletasks()

        content_w = self.content.winfo_reqwidth()
        content_h = self.content.winfo_reqheight()
        top_h     = self.topbar.winfo_reqheight()
        bot_h     = self.bot.winfo_reqheight()
        scroll_w  = self.vscroll.winfo_reqwidth() or 16

        pad_w = 30
        pad_h = 30

        desired_w = content_w + scroll_w + pad_w
        desired_h = top_h + content_h + bot_h + pad_h

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        
        # Allow up to 90% of screen, but prefer reasonable defaults
        max_w = int(sw * 0.90)
        max_h = int(sh * 0.90)
        
        # Start with a reasonable default, not cramped
        win_w = min(desired_w, max_w, 1400)  # cap at 1400px initially
        win_h = min(desired_h, max_h, 900)   # cap at 900px initially
        
        # Ensure minimum viable size
        win_w = max(win_w, 1024)
        win_h = max(win_h, 720)

        x = (sw - win_w) // 2
        y = max(0, (sh - win_h) // 3)
        self.geometry(f"{win_w}x{win_h}+{x}+{y}")

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _rebuild_all(self):
        """
        Rebuild BEFORE and AFTER grids using current THUMB_W/THUMB_H and 3 columns.
        """
        self._clear_image_refs(self.left_frame)
        self._clear_image_refs(self.right_frame)

        for w in self.left_frame.grid_slaves():
            w.destroy()
        for w in self.right_frame.grid_slaves():
            w.destroy()

        ttk.Label(
            self.left_frame,
            text="BEFORE",
            font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))

        ttk.Label(
            self.right_frame,
            text="AFTER (click to select, double-click to crop)",
            font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))

        self._build_group(self.left_frame,  self.before_paths, selectable=False, is_after=False)
        self._build_group(self.right_frame, self.after_paths, selectable=True, is_after=True)

        self._on_content_configure()

    def _on_content_configure(self, _evt=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, evt):
        canvas_width = evt.width
        self.canvas.itemconfigure(self.content_id, width=canvas_width)

        # The content has 3 columns: left_frame | center_bar | right_frame
        # Each frame should get roughly equal width
        # But center_bar is narrow, so allocate most space to left + right
        
        CENTER_BAR_WIDTH = 200  # fixed width for center buttons
        FRAME_PADDING = 10      # padding between frames (padx=5 each side)
        
        # Available width for left + right frames
        available_w = canvas_width - CENTER_BAR_WIDTH - FRAME_PADDING
        
        # Each side frame gets half
        side_frame_width = available_w // 2
        
        # Now divide each side frame into 3 columns of thumbnails
        per_col_padding = 20  # padding around each thumbnail
        total_padding = per_col_padding * self.COLS
        
        if side_frame_width <= total_padding:
            new_thumb_w = 80  # absolute minimum
        else:
            new_thumb_w = (side_frame_width - total_padding) // self.COLS
            new_thumb_w = min(320, max(100, new_thumb_w))  # clamp between 100-320
        
        new_thumb_h = new_thumb_w  # square thumbnails
        
        # Skip rebuild if nothing changed
        if new_thumb_w == self.THUMB_W and new_thumb_h == self.THUMB_H:
            return

        self.THUMB_W, self.THUMB_H = new_thumb_w, new_thumb_h

        # Debounce rebuild
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self._rebuild_all)

    def _enable_global_scroll(self):
        self.bind_all("<MouseWheel>", self._on_global_wheel, add="+")
        self.bind_all("<Button-4>",  self._on_global_wheel, add="+")
        self.bind_all("<Button-5>",  self._on_global_wheel, add="+")

    def _disable_global_scroll(self):
        try:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        except Exception:
            pass

    def _on_global_wheel(self, event):
        if event.widget.winfo_toplevel() is not self:
            return
        if not (self.canvas and self.canvas.winfo_exists()):
            return
        STEPS = 1
        try:
            if event.num == 4:
                self.canvas.yview_scroll(-STEPS, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(STEPS, "units")
            else:
                direction = -1 if event.delta > 0 else 1
                self.canvas.yview_scroll(direction * STEPS, "units")
        except tk.TclError:
            pass

    def _build_group(self, frame, paths, selectable, is_after):
        # clear existing rows (but first drop image refs so Tk can free bitmaps)
        self._clear_image_refs(frame)
        for w in frame.grid_slaves():
            if int(w.grid_info().get("row", 1)) >= 1:
                w.destroy()
        if is_after:
            self._after_labels.clear()

        for i, p in enumerate(paths):
            row = (i // self.COLS) * 2 + 1
            col = (i % self.COLS)

            if os.path.exists(p):
                try:
                    with Image.open(p) as im:
                        im.thumbnail((self.THUMB_W, self.THUMB_H))
                        ph = ImageTk.PhotoImage(im, master=self)   # <- tie to toplevel
                    img_label = tk.Label(frame, image=ph, relief="groove", bd=2)
                    img_label.image = ph  # <- keep only on the widget
                except Exception:
                    img_label = tk.Label(frame, text="(unreadable)", width=32, height=12, relief="groove")
            else:
                img_label = tk.Label(frame, text="(missing)", width=32, height=12, relief="groove")

            if selectable and is_after:
                idx = i
                img_label.bind("<Button-1>", lambda e, k=idx: self._select_after(k))
                img_label.bind("<Double-Button-1>", lambda e, k=idx: self._open_crop_tool(k))

            img_label.grid(row=row, column=col, padx=6, pady=6)

            order_num = display_order_for_path(p) or (i + 1)
            controls = tk.Frame(frame)
            controls.grid(row=row+1, column=col, pady=(0, 10))

            # left rotate
            btn_l = ttk.Button(controls, text="⟲", width=1.5,
                            command=lambda k=i: self._rotate_index(k, -90))
            btn_l.pack(side="left", padx=(0,10))
            Tooltip(btn_l, "Rotate left (hotkey: 4 or Left arrow)")

            # index image up
            btn_up = ttk.Button(controls, text="↑", width=1.5,
                                command=lambda k=i: self._image_index(k, 1))
            btn_up.pack(side="left", padx=4)
            Tooltip(btn_up, "Move image up (hotkey: Up arrow or 8)")

            # caption in the middle
            cap = tk.Label(controls, text=f"#{order_num}")
            cap.pack(side= "left", padx = (5,5))
            Tooltip(cap, f"{p} — display order #{order_num}")

            # index image down
            btn_up = ttk.Button(controls, text="↓", width=1.5,
                                command=lambda k=i: self._image_index(k, -1))
            btn_up.pack(side="left", padx=4)
            Tooltip(btn_up, "Move image down (hotkey: Down arrow or 2)")

            # right rotate
            btn_r = ttk.Button(controls, text="⟳", width=1.5,
                            command=lambda k=i: self._rotate_index(k, 90))
            btn_r.pack(side="left", padx=(10,0))
            Tooltip(btn_r, "Rotate right (hotkey: 6 or Right arrow)")

            if is_after:
                self._after_labels.append((img_label, cap))

    def _selected_image_index(self, direction: int):
        if not self._require_selection(): return
        self._image_index(self._selected_idx, direction)
        return

    def _image_index(self, idx: int, direction: int):
        """
        Move AFTER image at idx up/down by one position and
        renumber files on disk to 1..N according to scheme.
        direction: 1 = up (toward index 0), -1 = down.
        """
        if not (0 <= idx < len(self.after_paths)):
            return

        if direction == 1:  # move up
            if idx == 0:
                return  # already at top
            new_idx = idx - 1
        elif direction == -1:  # move down
            if idx == len(self.after_paths) - 1:
                return  # already at bottom
            new_idx = idx + 1
        else:
            return  # unknown direction, ignore

        # Reorder in-memory list
        self.after_paths[idx], self.after_paths[new_idx] = (
            self.after_paths[new_idx],
            self.after_paths[idx],
        )

        # Renumber file names on disk to match new order
        self._resequence_after_files()

        # Rebuild UI & keep selection on moved image
        self._build_group(self.right_frame, self.after_paths, selectable=True, is_after=True)
        self._select_after(new_idx)

    def _resequence_after_files(self):
        """
        Given current self.after_paths order (for a single lot),
        rename files on disk so that they become:

            lot(1).ext, lot(2).ext, ...         [paren]
            lot_1.ext, lot_2.ext, ...           [under]
            lot-1.ext, lot-2.ext, ...           [hyphen]

        according to whichever scheme that lot already uses.
        """
        plan = {}        # {src_abs: dst_abs}
        new_paths = []   # what after_paths *will* be after renames

        for new_idx, old_path in enumerate(self.after_paths, start=1):
            parsed = parse_image_name(old_path)
            if not parsed:
                # Non-matching: leave as-is
                new_paths.append(old_path)
                continue

            lot, _old_idx, scheme, ext = parsed

            # If somehow a 'bare' sneaks in, treat it as paren indexed
            if scheme == "bare":
                scheme = "paren"

            dst_name = _target_name(lot, new_idx, scheme, ext)
            dst_path = os.path.join(os.path.dirname(old_path), dst_name)
            new_paths.append(dst_path)

            if dst_path != old_path:
                plan[old_path] = dst_path

        if not plan:
            # Nothing to rename; just update paths
            self.after_paths = sort_paths_by_index(new_paths)
            return

        # Apply via shared safe renamer (handles cycles with temp files)
        _apply_renames(plan)

        # Update our in-memory paths to final names, and keep them sorted by index
        self.after_paths = sort_paths_by_index(new_paths)
    
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
        ord_after = display_order_for_path(after_p) or (idx + 1)
        match_before = None
        for p in self.before_paths:
            if (display_order_for_path(p) or -1) == ord_after:
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
            ord_after = display_order_for_path(after_p) or (i + 1)
            match_before = None
            for p in self.before_paths:
                if (display_order_for_path(p) or -1) == ord_after:
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
        after_p  = self.after_paths[idx]
        ord_after = display_order_for_path(after_p) or (idx + 1)
        before_p = None
        for p in self.before_paths:
            if (display_order_for_path(p) or -1) == ord_after:
                before_p = p; break
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
            ord_after = display_order_for_path(after_p) or (i + 1)
            before_p = None
            for p in self.before_paths:
                if (display_order_for_path(p) or -1) == ord_after:
                    before_p = p; break
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
        (lbl, _cap) = self._after_labels[idx]
        p = self.after_paths[idx]
        if os.path.exists(p):
            try:
                with Image.open(p) as im:
                    im.thumbnail((self.THUMB_W, self.THUMB_H))
                    ph = ImageTk.PhotoImage(im, master=self)
                lbl.configure(image=ph)
                # drop old ref first (helps GC)
                if hasattr(lbl, "image"):
                    lbl.image = None
                lbl.image = ph
            except Exception:
                lbl.configure(text="(unreadable)", image="", width=32, height=12)
                if hasattr(lbl, "image"):
                    lbl.image = None
        else:
            lbl.configure(text="(missing)", image="", width=32, height=12)
            if hasattr(lbl, "image"):
                lbl.image = None

    def _clear_image_refs(self, frame):
        for w in frame.grid_slaves():
            # if a label was holding a PhotoImage, drop the reference
            if hasattr(w, "image"):
                w.image = None
        gc.collect()

    def _rebuild_after(self):
        self._build_group(self.right_frame, self.after_paths, selectable=True, is_after=True)

    def _open_crop_tool(self, idx):
        self._select_after(idx)
        self._crop_selected()

    # ----- Reviewed-file helpers -----
    def _reviewed_file_path(self):
        if not self.out_dir:
            return None
        return os.path.join(self.out_dir, "reviewed.txt")

    def _append_reviewed(self, basenames):
        """Append basenames (iterable) to reviewed.txt, avoiding duplicates."""
        rf = self._reviewed_file_path()
        if not rf:
            return
        existing = set()
        try:
            with open(rf, "r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if ln:
                        existing.add(os.path.basename(ln))
        except FileNotFoundError:
            pass

        to_add = [b for b in basenames if b not in existing]
        if not to_add:
            return
        try:
            with open(rf, "a", encoding="utf-8") as fh:
                for b in to_add:
                    fh.write(b + "\n")
        except Exception:
            pass

    def _mark_current_lot_reviewed(self):
        """Mark all input images for current lot as reviewed (record basenames)."""
        # prefer before_paths as canonical input list; if absent, use after_paths
        sources = self.before_paths if self.before_paths else self.after_paths
        basenames = [os.path.basename(p) for p in sources]
        self._append_reviewed(basenames)

    def _mark_and_next(self, *a):
        try:
            self._mark_current_lot_reviewed()
        except Exception:
            pass
        if callable(self.on_next_lot):
            self.on_next_lot()

    def _mark_and_prev(self, *a):
        try:
            self._mark_current_lot_reviewed()
        except Exception:
            pass
        if callable(self.on_prev_lot):
            self.on_prev_lot()

    def _delete_selected(self):
        if not self._require_selection(): return
        idx = self._selected_idx
        path = self.after_paths[idx]
        base = os.path.basename(path)
        resp = messagebox.askyesno("Delete", f"Delete {base}? This will skip it in future runs.")
        if not resp:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            messagebox.showerror("Delete", f"Failed to delete: {e}")
            return

        # record as reviewed (so it will be skipped in future)
        try:
            self._append_reviewed([base])
        except Exception:
            pass

        # remove from in-memory list and rebuild UI
        try:
            del self.after_paths[idx]
        except Exception:
            pass
        self._rebuild_after()