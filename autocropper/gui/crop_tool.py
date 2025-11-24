import os
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

# Crop Tool Window (drag rectangle to crop)
class CropTool(tk.Toplevel):
    # Initialize the window
    def __init__(self, master, image_path, on_apply):
        super().__init__(master)
        self.title(f"Crop: {os.path.basename(image_path)}")
        self.geometry("1200x800")
        self.minsize(900, 650)
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

        # Make Enter apply and close, Escape cancels
        self.bind("<Return>", lambda e: self._apply_crop())
        self.bind("<KP_Enter>", lambda e: self._apply_crop())  # numpad Enter
        self.bind("<Escape>",  lambda e: self.destroy())
        self.focus_force()

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
        
    def _apply_crop(self, e = None):
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