from collections import defaultdict
import threading
from ultralytics import YOLO
import cv2
import os, time, shutil, re
from tqdm import tqdm
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sv_ttk
from PIL import Image, ImageTk

current_idx=0

# Load YOLO model
try:
    model = YOLO("E:/Python Projects/auto_cropper/BDAuctions_lot_cropper/yolo11l.pt")
    print("Model Loaded")
except Exception as e:
    print(f"Failed to load model: {e}")
    messagebox.showinfo(f"Failed to load model: {e}")


class CropperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Cropper")
        self.root.geometry("550x325")

        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()

        # Input Folder Selection
        ttk.Label(root, text="Input Folder:").pack(pady=(10,0))
        ttk.Entry(root, textvariable=self.input_dir, width=60).pack()
        ttk.Button(root, text="Browse", command=self.select_input_folder).pack()

        # Output Folder Selection
        ttk.Label(root, text="Output Folder:").pack(pady=(10,0))
        ttk.Entry(root, textvariable=self.output_dir, width=60).pack()
        ttk.Button(root, text="Browse", command=self.select_output_folder).pack()

        # Run Button
        ttk.Button(root, text="Run Cropper", command=self.run).pack(pady=40)

    def select_input_folder(self):
        path = filedialog.askdirectory(title="Select Input Folder")
        if path:
            self.input_dir.set(path)

    def select_output_folder(self):
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_dir.set(path)

    def run(self):
        in_dir = self.input_dir.get()
        out_dir = self.output_dir.get()

        if not os.path.isdir(in_dir) or not os.path.isdir(out_dir):
            messagebox.showerror("Invalid Input", "Please select valid folders.")
            return
        
        def begin_Review():
            grouped_input = group_images_by_lot(in_dir)
            grouped_output = group_images_by_lot(out_dir)

            # grouped_input / grouped_output are dicts: lot_id(str) -> [paths...]
            all_lot_ids = set(grouped_input.keys()) | set(grouped_output.keys())
            lot_list = numeric_first_sort(all_lot_ids)  # e.g., ['12','13','101','A5']
            ReviewController(self.root, lot_list, grouped_input, grouped_output)

        root.withdraw()
        run_cropper(in_dir, out_dir, self.root, begin_Review)
        root.mainloop()

        
# GUI progress window class
# Provides the user an interface to monitor the progress of the model
# and the associated cropping
class ProgressWindow(tk.Toplevel):
    def __init__(self, master, total_items):
        super().__init__(master)
        self.title("Processing...")
        self.geometry("400x150")
        self.resizable(False, False)

        self.total_items = total_items
        self.start_time = time.time()

        self.label_status = ttk.Label(self, text="Starting cropping...")
        self.label_status.pack(pady=(10, 5))

        self.progress = ttk.Progressbar(self, length=300, mode='determinate', maximum=total_items)
        self.progress.pack(pady=5)

        self.label_eta = ttk.Label(self, text="Estimated time remaining: Calculating...")
        self.label_eta.pack(pady=(5, 10))

        self.label_count = ttk.Label(self, text=f"Cropped 0 of {total_items}")
        self.label_count.pack()

    # Updates the progress window. 
    # Includes estimated time and number of images cropped out of the total images.
    # Also advances the progress bar
    def update_progress(self, current):
        elapsed = time.time() - self.start_time
        rate = current / elapsed if elapsed > 0 else 0
        remaining = (self.total_items - current) / rate if rate > 0 else 0
        self.progress['value'] = current
        self.label_status.config(text="Cropping in progress...")
        self.label_eta.config(text=f"Estimated time remaining: {int(remaining)}s")
        self.label_count.config(text=f"Cropped {current} of {self.total_items}")
        self.update_idletasks()

def run_cropper(input_dir,output_dir,master,callback_func):
    # Mark input and output folders
    #input_dir = "E:/Python Projects/auto_cropper/BDAuctions_lot_cropper/test_input"
    #output_dir = "E:/Python Projects/auto_cropper/BDAuctions_lot_cropper/test_output"
    #os.makedirs(output_dir, exist_ok=True)
    
    image_files = [f for f in os.listdir(input_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]

    # create window for the progress bar and info
    win = ProgressWindow(master, len(image_files))

    # Define cropping loop to be called on another thread
    # that isn't clogged with the GUI
    def crop_loop():
        for i, filename in enumerate(image_files):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            auto_crop_detected_objects(input_path, output_path)
            win.update_progress(i)

        # Notice of completion in progress window
        win.label_status.config(text="Cropping Complete")
        win.label_eta.config(text="Done.")

        # Give time for it to be read
        time.sleep(1)

        # Withdraw progress window for completion message
        win.destroy()

        messagebox.showinfo("SUCCESS! Processing Complete", f"Cropped images saved to:\n{output_dir}")

        # Callback to the review display function when the thread closes.
        master.after(0, callback_func)

    # Work thread
    thread = threading.Thread(target=crop_loop, daemon=True)
    thread.start()

# Auto cropping function which loads image from the folder, predicts
# the location of objects and combines all boxes into 
def auto_crop_detected_objects(image_path, output_path):
    global model
    image = cv2.imread(image_path)
    if image is None:
        print(f"Failed to load {image_path}")
        return

    results = model.predict(image_path, conf=0.000000001, imgsz=4800, verbose=False)[0]

    class_ids = [int(cls.item()) for cls in results.boxes.cls]
    class_names = [model.names[i] for i in class_ids]
    print(f"Detected: {set(class_names)} in {os.path.basename(image_path)}")

    if results.boxes is None or len(results.boxes) == 0:
        print(f"No objects detected in {image_path}")
        cv2.imwrite(output_path, image)
        return

    # Get all bounding boxes detected, including noise boxes from underfitting 
    # the model to the images
    boxes = results.boxes.xyxy.cpu().numpy()

    # Filter out very small boxes by area (e.g., noise)
    img_area = image.shape[0] * image.shape[1]
    min_area = 0.0026 * img_area
    valid_boxes = []
    for box in boxes:
        x1, y1, x2, y2 = box[:4]
        area = (x2 - x1) * (y2 - y1)
        if area >= min_area:
            valid_boxes.append(box)

    # Check some boxes remain
    if not valid_boxes:
        print(f"Only tiny objects detected in {image_path}, skipping crop")
        cv2.imwrite(output_path, image)
        return

    # Combine all of the filtered boxes into one large box
    valid_boxes = np.array(valid_boxes)
    x_min = int(np.min(valid_boxes[:, 0]))
    y_min = int(np.min(valid_boxes[:, 1]))
    x_max = int(np.max(valid_boxes[:, 2]))
    y_max = int(np.max(valid_boxes[:, 3]))

    # Add margin
    margin = 20
    x_min = max(0, x_min - margin)
    y_min = max(0, y_min - margin)
    x_max = min(image.shape[1], x_max + margin)
    y_max = min(image.shape[0], y_max + margin)

    # Crop the image down and write it to the output
    cropped = image[y_min:y_max, x_min:x_max]
    cv2.imwrite(output_path, cropped)
    print(f"Cropped and saved: {output_path}")

def group_images_by_lot(folder):
    pattern = re.compile(r"(\d+)(?:\s*\(\d+\))?\.(jpg|jpeg|png)$", re.IGNORECASE)
    lot_dict = defaultdict(list)
    
    for filename in os.listdir(folder):
        match = pattern.match(filename)
        if match:
            lot_number = match.group(1)
            lot_dict[lot_number].append(os.path.join(folder, filename))
    
    return lot_dict

_IDX_PAT = re.compile(r"\((\d+)\)")

def _order_index(path_or_name, default_idx):
    name = os.path.basename(path_or_name)
    m = _IDX_PAT.search(name)
    if m:
        try:
            return int(m.group(1))
        except:
            pass
    return default_idx

def _natural_sort_by_index(paths):
    return sorted(paths, key=lambda p: _order_index(p, 10**9))

# ---- Crop Tool Window (drag rectangle over image, then Apply) ----
class CropTool(tk.Toplevel):
    def __init__(self, master, image_path, on_apply):
        super().__init__(master)
        self.title(f"Crop: {os.path.basename(image_path)}")
        self.geometry("1200x800")           # larger default window
        self.minsize(900, 650)              # prevent too small
        self.resizable(True, True)
        self.on_apply = on_apply
        self.image_path = image_path

        # Load image
        self.img_full = Image.open(image_path)
        self.img_disp = self.img_full.copy()

        # === Canvas with PALE ORANGE background ===
        self.canvas = tk.Canvas(self, bg="#FFE8CC", highlightthickness=0)  # pale orange
        self.canvas.pack(fill="both", expand=True)

        # Buttons row
        btnbar = tk.Frame(self)
        btnbar.pack(fill="x", pady=(4, 10))
        ttk.Button(btnbar, text="Apply Crop", command=self._apply_crop).pack(side="left", padx=6)
        ttk.Button(btnbar, text="Cancel",     command=self.destroy).pack(side="right", padx=6)

        # INTERNAL canvas margins (so blank space is part of the canvas)
        self.pad_left   = 10
        self.pad_right  = 10
        self.pad_top    = 40   # formerly your top spacer height
        self.pad_bottom = 40   # bottom breathing room

        # Redraw image on resize
        self.bind("<Configure>", self._resize_fit)

        # Mouse rectangle selection
        self._rect_id = None
        self._overlay_ids = []   # four orange overlay rects around selection
        self._start = None
        self._end = None
        self._scale = 1.0
        self._offset = (0, 0)

        self.canvas.bind("<Button-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_up)

        self._photo = None
        self._draw_image()

    def _resize_fit(self, _evt=None):
        self._draw_image()

    def _draw_image(self):
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)

        # available content area INSIDE the canvas margins
        content_w = max(cw - (self.pad_left + self.pad_right), 1)
        content_h = max(ch - (self.pad_top + self.pad_bottom), 1)

        iw, ih = self.img_full.size
        scale = min(content_w/iw, content_h/ih)
        dw, dh = max(int(iw*scale), 1), max(int(ih*scale), 1)
        self.img_disp = self.img_full.resize((dw, dh), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(self.img_disp)

        self.canvas.delete("all")

        # center the image within the content area, honoring margins
        ox = self.pad_left + (content_w - dw)//2
        oy = self.pad_top  + (content_h - dh)//2
        self._offset = (ox, oy)
        self._scale = scale

        # draw image
        self.canvas.create_image(ox, oy, anchor="nw", image=self._photo)

        # if a selection exists, redraw overlays/rect
        if self._start and self._end:
            self._draw_overlays_and_rect()

    def _on_down(self, e):
        self._start = (e.x, e.y)
        self._end = (e.x, e.y)
        self._draw_overlays_and_rect()

    def _on_drag(self, e):
        self._end = (e.x, e.y)
        self._draw_overlays_and_rect()

    def _on_up(self, e):
        self._end = (e.x, e.y)
        self._draw_overlays_and_rect()

    def _draw_overlays_and_rect(self):
        # Remove old overlays and rect
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None
        for oid in self._overlay_ids:
            self.canvas.delete(oid)
        self._overlay_ids.clear()

        if not (self._start and self._end):
            return

        # Selection bounds
        x1, y1 = self._start
        x2, y2 = self._end
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))

        # Image display bounds
        ox, oy = self._offset
        iw, ih = self.img_disp.size
        left   = ox
        right  = ox + iw
        top    = oy
        bottom = oy + ih

        # Semi-transparent gray fill with outline
        self._rect_id = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="#00ffff",
            width=2,
            fill="#808080",
            stipple="gray50"
        )
        
    def _apply_crop(self):
        if not (self._start and self._end):
            messagebox.showwarning("Crop", "Draw a rectangle first.")
            return

        ox, oy = self._offset
        scale = self._scale
        x1, y1 = self._start
        x2, y2 = self._end
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))

        # Canvas -> image coords
        ix1 = int((x1 - ox) / scale);  iy1 = int((y1 - oy) / scale)
        ix2 = int((x2 - ox) / scale);  iy2 = int((y2 - oy) / scale)

        iw, ih = self.img_full.size
        ix1 = max(0, min(ix1, iw - 1));  iy1 = max(0, min(iy1, ih - 1))
        ix2 = max(1, min(ix2, iw));      iy2 = max(1, min(iy2, ih))

        if ix2 <= ix1 or iy2 <= iy1:
            messagebox.showwarning("Crop", "Invalid crop area.")
            return

        cropped = self.img_full.crop((ix1, iy1, ix2, iy2))
        self.on_apply(cropped)
        self.destroy()

class ReviewController:
    def __init__(self, root, lot_list, grouped_input, grouped_output):
        self.root = root
        self.lot_list = lot_list
        self.gi = grouped_input
        self.go = grouped_output
        self.idx = 0

        lot = self.lot_list[self.idx]
        self.win = LotReviewWindow(
            master=root,
            lot_number=lot,
            before_paths=self.gi.get(lot, []),
            after_paths=self.go.get(lot, []),
            on_prev_lot=self.prev,
            on_next_lot=self.next,
        )

    def open_idx(self, i):
        self.idx = max(0, min(i, len(self.lot_list)-1))
        lot = self.lot_list[self.idx]
        self.win.set_lot(lot, self.gi.get(lot, []), self.go.get(lot, []))

    def prev(self): self.open_idx(self.idx - 1)
    def next(self): self.open_idx(self.idx + 1)

class LotReviewWindow(tk.Toplevel):
    def __init__(self, master, lot_number, before_paths, after_paths,
                on_prev_lot, on_next_lot):
        super().__init__(master)
        self.title(f"Lot {lot_number} — Review")
        self.lot_number = str(lot_number)
        self.before_paths = _natural_sort_by_index(before_paths)
        self.after_paths  = _natural_sort_by_index(after_paths)
        self.on_prev_lot = on_prev_lot
        self.on_next_lot = on_next_lot

        self.THUMB_W, self.THUMB_H = 280, 280
        self.COLS = 3
        self._selected_idx = None
        self._after_labels = []
        self._photo_refs = []

        # TOP toolbar (fixed)
        self.topbar = ttk.Frame(self)
        self.topbar.pack(fill="x", pady=(8, 4))

        self.header_label = ttk.Label(self.topbar, text=f"Lot {self.lot_number}", font=("Segoe UI", 12, "bold"))
        self.header_label.pack(side="left", padx=8)

        ttk.Button(self.topbar, text="⟲ Rotate Left",  command=lambda: self._rotate_selected(-90)).pack(side="right", padx=4)
        ttk.Button(self.topbar, text="⟳ Rotate Right", command=lambda: self._rotate_selected(90)).pack(side="right", padx=4)
        ttk.Button(self.topbar, text="✂ Crop",         command=self._crop_selected).pack(side="right", padx=4)

        # ==== SCROLLABLE MID AREA (both groups scroll together) ====
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=6)

        self.canvas = tk.Canvas(mid, highlightthickness=0)
        vscroll = ttk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vscroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        # The frame that actually holds the grids
        self.content = ttk.Frame(self.canvas)
        self.content_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        # Update scrollregion whenever content changes size
        self.content.bind("<Configure>", self._on_content_configure)
        # Resize inner window width to match canvas width
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse wheel scrolling (Windows/macOS/Linux)
        self._bind_mousewheel(self.canvas)

        # Inside content: left/right frames + center bar
        self.left_frame  = tk.Frame(self.content)   # BEFORE
        self.center_bar  = tk.Frame(self.content)   # actions
        self.right_frame = tk.Frame(self.content)   # AFTER

        self.left_frame.grid(row=0, column=0, sticky="n", padx=(0,10))
        self.center_bar.grid(row=0, column=1, sticky="ns", padx=10)
        self.right_frame.grid(row=0, column=2, sticky="n", padx=(10,0))

        # Headers
        ttk.Label(self.left_frame,  text="BEFORE", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))
        ttk.Label(self.right_frame, text="AFTER (click to select, double-click to crop)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))

        # Center actions
        ttk.Button(self.center_bar, text="↩ Revert Selected", width=18, command=self._revert_selected).pack(pady=6)
        ttk.Button(self.center_bar, text="↩↩ Revert All",     width=18, command=self._revert_all).pack(pady=6)
        ttk.Separator(self.center_bar, orient="horizontal").pack(fill="x", pady=6)
        ttk.Button(self.center_bar, text="♻ Recrop All",      width=18, command=self._recrop_all).pack(pady=6)
        ttk.Button(self.center_bar, text="♻ Recrop Selected", width=18, command=self._recrop_selected).pack(pady=6)

        # Build grids into left/right frames
        self._build_group(self.left_frame,  self.before_paths, selectable=False, is_after=False)
        self._build_group(self.right_frame, self.after_paths,  selectable=True,  is_after=True)

        # ==== BOTTOM NAV (fixed) ====
        bot = tk.Frame(self)
        bot.pack(fill="x", pady=8)
        ttk.Button(bot, text="⟵ Prev Lot", command=self.on_prev_lot).pack(side="left", padx=10)
        ttk.Button(bot, text="Next Lot ⟶", command=self.on_next_lot).pack(side="right", padx=10)

        self.minsize(1024, 720)

    def set_lot(self, lot_number, before_paths, after_paths):
        """Swap to a new lot without opening a new window."""
        self.lot_number = str(lot_number)
        self.before_paths = _natural_sort_by_index(before_paths)
        self.after_paths  = _natural_sort_by_index(after_paths)
        self._selected_idx = None

        # Update window title and header text
        self.title(f"Lot {self.lot_number} — Review")
        self.header_label.configure(text=f"Lot {self.lot_number}")

        # Rebuild both sides
        for w in self.left_frame.grid_slaves():
            if int(w.grid_info().get("row", 1)) >= 0:
                w.destroy()
        for w in self.right_frame.grid_slaves():
            if int(w.grid_info().get("row", 1)) >= 0:
                w.destroy()

        ttk.Label(self.left_frame,  text="BEFORE", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))
        ttk.Label(self.right_frame, text="AFTER (click to select, double-click to crop)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.COLS, pady=(0, 8))

        self._build_group(self.left_frame,  self.before_paths, selectable=False, is_after=False)
        self._build_group(self.right_frame, self.after_paths,  selectable=True,  is_after=True)

        # Refresh scroll region
        self._on_content_configure()
        
    # ----- scroll helpers -----
    def _on_content_configure(self, _evt=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, evt):
        # Make inner frame match canvas width for nice resizing
        canvas_width = evt.width
        self.canvas.itemconfigure(self.content_id, width=canvas_width)

    def _bind_mousewheel(self, widget):
        # Windows / Linux
        widget.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        # macOS
        widget.bind_all("<Button-4>", self._on_mousewheel, add="+")
        widget.bind_all("<Button-5>", self._on_mousewheel, add="+")

    def _on_mousewheel(self, event):
        if event.num == 4:      # macOS scroll up
            self.canvas.yview_scroll(-3, "units")
        elif event.num == 5:    # macOS scroll down
            self.canvas.yview_scroll(3, "units")
        else:                   # Windows/Linux
            delta = int(-1 * (event.delta / 120))
            self.canvas.yview_scroll(delta, "units")

    # ----- build grids (unchanged logic) -----
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

    # ----- selection & actions (same as before; keep your implementations) -----
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
    
    # ---- Actions: rotate / crop / revert / recrop ----
    def _rotate_selected(self, deg):
        if not self._require_selection(): return
        idx = self._selected_idx
        path = self.after_paths[idx]
        if not os.path.exists(path):
            messagebox.showerror("Rotate", "Selected image is missing.")
            return
        try:
            im = Image.open(path)
            im = im.rotate(-deg, expand=True)  # PIL rotates counter-clockwise; negate for UI intuition
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
        # find matching before path by order number (best-effort)
        ord_after = _order_index(after_p, idx+1)
        match_before = None
        for p in self.before_paths:
            if _order_index(p, -1) == ord_after:
                match_before = p
                break
        # fallback: same index
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
            # match by order number
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
            auto_crop_detected_objects(before_p, after_p)  # <- Your YOLO cropper here
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
                    auto_crop_detected_objects(before_p, after_p)  # <- Your YOLO cropper here
                    count += 1
                except Exception as e:
                    print("Recrop error:", e)
        self._rebuild_after()
        messagebox.showinfo("Recrop All", f"Recropped {count} images.")

    # ---- Refresh helpers ----
    def _refresh_after(self, idx):
        # Just redraw the one after tile
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

    # ---- Double-click on AFTER → open crop tool ----
    def _open_crop_tool(self, idx):
        self._select_after(idx)
        self._crop_selected()

def numeric_first_sort(keys):
    def keyfn(k):
        # Try numeric sort; if not numeric, push after numbers and sort lexicographically
        try:
            return (0, int(k))
        except ValueError:
            return (1, str(k))
    return sorted(keys, key=keyfn)


if __name__ == "__main__":
    root = tk.Tk()
    sv_ttk.set_theme("light")
    app = CropperGUI(root)
    root.mainloop()