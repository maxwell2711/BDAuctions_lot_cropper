import os
import tkinter as tk
from tkinter import messagebox
from ultralytics import YOLO
import torch

MODEL_FILENAME = "yolo11x.pt"  # put this in the package root (next to app.py)

_model_singleton = None

def get_model():
    """Load YOLO once (GPU if available), reuse thereafter."""
    global _model_singleton
    if _model_singleton is not None:
        return _model_singleton

    base_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(base_dir, MODEL_FILENAME)

    # Try loading the model (on GPU hopefully)
    try:
        model = YOLO(model_path)
        if torch.cuda.is_available():
            model.to("cuda:0")
        else:
            model.to("cpu")
        _model_singleton = model
        return _model_singleton
    except Exception as e:
        # Safe to show a dialog because app has Tk root
        try:
            messagebox.showerror("Model load failed", f"Failed to load model:\n{e}")
        except tk.TclError:
            pass
        raise