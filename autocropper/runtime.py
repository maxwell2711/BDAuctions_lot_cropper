# Shared runtime/state to avoid circular imports
from types import SimpleNamespace
import threading
import cv2

# Progress struct used by worker + progress window
progress = SimpleNamespace(
    current=0,
    total=0,
    current_file="",
    running=False,
)

# Global stop event (set on cancel/close)
stop_event = threading.Event()

# Idempotent shutdown hook (set by app.py)
_shutdown_called = False

def on_root_close(root):
    """Idempotent: cleans up OpenCV windows and closes Tk app."""
    global _shutdown_called
    if _shutdown_called:
        return
    _shutdown_called = True

    try:
        stop_event.set()
    except Exception:
        pass
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass

    try:
        root.after(0, lambda: (root.quit(), root.destroy()))
    except Exception:
        pass