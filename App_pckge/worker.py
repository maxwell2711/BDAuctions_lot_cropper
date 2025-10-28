import os, threading, time
import tkinter as tk
from tkinter import ttk
from .runtime import progress, stop_event, on_root_close
from .cropper import auto_crop_detected_objects

class ProgressWindow(tk.Toplevel):
    # Initialize and format the window
    def __init__(self, master, total_items):
        super().__init__(master)
        self.title("Processing...")
        self.geometry("540x175")
        self.resizable(False, False)
        self.total_items = total_items
        self.start_time = time.time()

        self.label_status = ttk.Label(self, text="Starting cropping...")
        self.label_status.pack(pady=(10, 5))

        self.busy = ttk.Progressbar(self, length=280, mode='indeterminate')
        self.busy.pack(pady=(4, 6))
        self.busy.start(12)

        self.progress = ttk.Progressbar(self, length=480, mode='determinate', maximum=total_items)
        self.progress.pack(pady=(45,6))

        self.label_eta = ttk.Label(self, text="Estimated time remaining: Calculating...")
        self.label_eta.pack(pady=(0, 6))

        self.label_count = ttk.Label(self, text=f"Cropped 0 of {total_items}")
        self.label_count.pack()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_id = self.after(100, self._poll_progress)

    # Handle close event
    def _on_close(self):
        stop_event.set()
        progress.running = False
        if self._poll_id is not None:
            try: self.after_cancel(self._poll_id)
            except Exception: pass
            self._poll_id = None
        try: self.destroy()
        except tk.TclError: pass
        on_root_close(self.master)

    # Update the poll window independent of callbacks
    def _poll_progress(self):
        if not self.winfo_exists():
            return
        try:
            cur = min(progress.current, self.total_items)
            self.progress['value'] = cur
            self.label_count.config(text=f"Cropped {cur} of {self.total_items}")

            elapsed = max(0.001, time.time() - self.start_time)
            rate = cur / elapsed
            remain = int((self.total_items - cur) / rate) if rate > 0 else 0
            self.label_eta.config(text=f"Estimated time remaining: {remain}s")

            if progress.current_file:
                self.label_status.config(text=f"Cropping: {os.path.basename(progress.current_file)}")
            else:
                self.label_status.config(text="Cropping in progress...")
        except tk.TclError:
            return

        if progress.running and cur < self.total_items and not stop_event.is_set():
            self._poll_id = self.after(200, self._poll_progress)
        else:
            self._poll_id = None
            try:
                self.busy.stop()
            except tk.TclError:
                pass

def run_cropper(input_dir, output_dir, master, on_done):
    # Mark input and output folders
    #input_dir = "E:/Python Projects/auto_cropper/BDAuctions_lot_cropper/test_input"
    #output_dir = "E:/Python Projects/auto_cropper/BDAuctions_lot_cropper/test_output"
    #os.makedirs(output_dir, exist_ok=True)
    image_files = [f for f in os.listdir(input_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]

    progress.current = 0
    progress.total = len(image_files)
    progress.current_file = ""
    progress.running = True

    # Create progress bar window
    win = ProgressWindow(master, len(image_files))

    # Define cropping loop to be called on another thread
    # that isn't clogged with the GUI
    def crop_loop():
        for filename in image_files:
            if stop_event.is_set():
                break
            src = os.path.join(input_dir, filename)
            dst = os.path.join(output_dir, filename)
            # Update progress bar before cropping
            progress.current_file = src
            # Crop
            auto_crop_detected_objects(src, dst)
            # Inc cropped objects
            progress.current += 1
            if stop_event.is_set():
                break

        progress.running = False

        # Finish UI on main thread
        def finish_ui():
            if not win.winfo_exists():
                return
            try:
                win.busy.stop()
            except tk.TclError:
                pass
            
            # Window is closed by user. Destroy window and reshow root
            if stop_event.is_set():
                try: win.destroy()
                except tk.TclError: pass
                try: master.deiconify()
                except Exception: pass
                return

            # Normal Completion
            win.label_status.config(text="Cropping Complete")
            win.label_eta.config(text="Done.")
            win.after(300, lambda: (
                win.destroy(),
                master.after(0, on_done)
            ))
        # finish_ui runs after the thread has closed 
        master.after(0, finish_ui)

    # Worker thread for cropping
    threading.Thread(target=crop_loop, daemon=True).start()