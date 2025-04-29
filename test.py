from ultralytics import YOLO
import numpy

# Load a model
model = YOLO("yolov8n.pt")  # Or use yolov8x.pt if you want bigger

# Run inference on an image
results = model.predict(source="https://ultralytics.com/images/bus.jpg", save=True)

print("Detection complete!")