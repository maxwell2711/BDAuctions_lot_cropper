from collections import defaultdict
import threading
from ultralytics import YOLO
import cv2
import os, time
from tqdm import tqdm
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os, re
from PIL import Image, ImageTk



class CropperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Cropper")
        self.root.geometry("500x250")

        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()

        # Input Folder Selection
        tk.Label(root, text="Input Folder:").pack(pady=(10,0))
        tk.Entry(root, textvariable=self.input_dir, width=60).pack()
        tk.Button(root, text="Browse", command=self.select_input_folder).pack()

        # Output Folder Selection
        tk.Label(root, text="Output Folder:").pack(pady=(10,0))
        tk.Entry(root, textvariable=self.output_dir, width=60).pack()
        tk.Button(root, text="Browse", command=self.select_output_folder).pack()

        # Run Button
        tk.Button(root, text="Run Cropper", command=self.run).pack(pady=40)

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
            display_lot_images(in_dir,out_dir,grouped_input,grouped_output,503)

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

        self.label_status = tk.Label(self, text="Starting cropping...")
        self.label_status.pack(pady=(10, 5))

        self.progress = ttk.Progressbar(self, length=300, mode='determinate', maximum=total_items)
        self.progress.pack(pady=5)

        self.label_eta = tk.Label(self, text="Estimated time remaining: Calculating...")
        self.label_eta.pack(pady=(5, 10))

        self.label_count = tk.Label(self, text=f"Cropped 0 of {total_items}")
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

    # Load YOLO model
    try:
        model = YOLO("E:/Python Projects/auto_cropper/BDAuctions_lot_cropper/yolov8x.pt")
        print("Model Loaded")
    except Exception as e:
        print(f"Failed to load model: {e}")
        messagebox.showinfo(f"Failed to load model: {e}")

    image_files = [f for f in os.listdir(input_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]

    # create window for the progress bar and info
    win = ProgressWindow(master, len(image_files))

    # Define cropping loop to be called on another thread
    # that isn't clogged with the GUI
    def crop_loop():
        for i, filename in enumerate(image_files):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            auto_crop_detected_objects(input_path, output_path, model)
            win.update_progress(i)

        # Notice of completion in progress window
        win.label_status.config(text="Cropping Complete")
        win.label_eta.config(text="Done.")

        # Give time for it to be read
        time.sleep(2)

        # Withdraw progress window for completion message
        win.withdraw()

        messagebox.showinfo("SUCCESS! Processing Complete", f"Cropped images saved to:\n{output_dir}")

        # Callback to the review display function when the thread closes.
        master.after(0, callback_func)

    # Work thread
    thread = threading.Thread(target=crop_loop, daemon=True)
    thread.start()


# Auto cropping function which loads image from the folder, predicts
# the location of objects and combines all boxes into 
def auto_crop_detected_objects(image_path, output_path, model):
    image = cv2.imread(image_path)
    if image is None:
        print(f"Failed to load {image_path}")
        return

    results = model.predict(image_path, conf=0.0000000000000001, imgsz=4800, verbose=False)[0]

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

def display_lot_images(input_dir, output_dir, grouped_input, grouped_output, lot_number):
    """Creates a Tkinter window showing before/after images side by side for a given lot."""
    window = tk.Toplevel()
    window.title(f"Lot {lot_number} - Before and After")

    print(grouped_input[503])
    before_images = sorted(grouped_input[lot_number])
    after_images = sorted(grouped_output.get(lot_number, []))

    max_images = max(len(before_images), len(after_images))
    rows = (max_images + 3) // 4

    for i in range(max_images):
        before_img_path = os.path.join(input_dir, before_images[i]) if i < len(before_images) else None
        after_img_path = os.path.join(output_dir, after_images[i]) if i < len(after_images) else None

        if before_img_path and os.path.exists(before_img_path):
            before_img = Image.open(before_img_path)
            before_img.thumbnail((200, 200))
            tk_before = ImageTk.PhotoImage(before_img)
            label = tk.Label(window, image=tk_before, text="Before", compound='top')
            label.image = tk_before
            label.grid(row=i // 4, column=(i % 4) * 2)

        if after_img_path and os.path.exists(after_img_path):
            after_img = Image.open(after_img_path)
            after_img.thumbnail((200, 200))
            tk_after = ImageTk.PhotoImage(after_img)
            label = tk.Label(window, image=tk_after, text="After", compound='top')
            label.image = tk_after
            label.grid(row=i // 4, column=(i % 4) * 2 + 1)

    window.mainloop()


if __name__ == "__main__":
    root = tk.Tk()
    app = CropperGUI(root)
    root.mainloop()