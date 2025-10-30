import tkinter as tk
import sv_ttk
from .runtime import on_root_close, stop_event
from .gui.rootgui import CropperGUI

# Entry point for the program
def main():
    root = tk.Tk()
    root.protocol("WM_DELETE_WINDOW", lambda: on_root_close(root))
    sv_ttk.set_theme("light")
    app = CropperGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()