import os
import cv2
import numpy as np
from .model import get_model

# Auto cropping function which loads image from the folder, predicts
# the location of objects and combines all boxes into one rectangle
def auto_crop_detected_objects(image_path, output_path):
    # Load the model
    model = get_model()

    image = cv2.imread(image_path)
    if image is None:
        print(f"Failed to load {image_path}")
        return

    # Predict the boxes for the image
    try:
        results = model.predict(
            image_path,
            device=0,          # or 'cuda'/'cpu'
            workers=0,         # safer with tkinter on Windows
            imgsz=4800,
            conf=1.5e-3,
            iou=0.18,
            max_det=200,
            agnostic_nms=True,
            half=True,
            amp=False,
            verbose=True
        )[0]
    except Exception as e:
        print("YOLO predict error:", e)
        results = None

    # Check for empty result
    if not results or results.boxes is None or len(results.boxes) == 0:
        print(f"No objects detected in {image_path}")
        cv2.imwrite(output_path, image)
        return

    boxes = results.boxes.xyxy.cpu().numpy()

    # Additional Post-processing
    # Aggregate all boxes with sufficient size
    img_area = image.shape[0] * image.shape[1]
    min_area = 0.0026 * img_area
    valid = []
    for x1, y1, x2, y2, *rest in boxes:
        area = (x2 - x1) * (y2 - y1)
        if area >= min_area:
            valid.append([x1, y1, x2, y2])

    if not valid:
        print(f"Only tiny objects in {image_path}, skipping crop")
        cv2.imwrite(output_path, image)
        return

    # Find the largest rectangle from all of the boxes in valid
    v = np.array(valid)
    x_min = int(np.min(v[:, 0])); y_min = int(np.min(v[:, 1]))
    x_max = int(np.max(v[:, 2])); y_max = int(np.max(v[:, 3]))

    margin = 20
    x_min = max(0, x_min - margin)
    y_min = max(0, y_min - margin)
    x_max = min(image.shape[1], x_max + margin)
    y_max = min(image.shape[0], y_max + margin)

    # Write the cropped image to the output
    cropped = image[y_min:y_max, x_min:x_max]
    cv2.imwrite(output_path, cropped)
    print(f"Cropped and saved: {output_path}")