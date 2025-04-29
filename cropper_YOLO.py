from ultralytics import YOLO
import cv2
import os
from tqdm import tqdm
import numpy as np

def main():
    input_dir = "E:/Python Projects/auto_cropper/BDAuctions_lot_cropper/test_input"
    output_dir = "E:/Python Projects/auto_cropper/BDAuctions_lot_cropper/test_output"
    os.makedirs(output_dir, exist_ok=True)

    # Load YOLO model
    try:
        model = YOLO("E:/Python Projects/auto_cropper/BDAuctions_lot_cropper/yolov8x.pt")
        print("Model Loaded")
    except Exception as e:
        print(f"Failed to load model: {e}")

    for filename in tqdm(os.listdir(input_dir)):
        if filename.lower().endswith((".jpg", ".png", ".jpeg")):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            auto_crop_detected_objects(input_path, output_path, model)

def auto_crop_detected_objects(image_path, output_path, model):
    image = cv2.imread(image_path)
    if image is None:
        print(f"Failed to load {image_path}")
        return

    results = model.predict(image_path, conf=0.000000000000000001, imgsz=4800, verbose=False)[0]

    class_ids = [int(cls.item()) for cls in results.boxes.cls]
    class_names = [model.names[i] for i in class_ids]
    print(f"Detected: {set(class_names)} in {os.path.basename(image_path)}")

    if results.boxes is None or len(results.boxes) == 0:
        print(f"No objects detected in {image_path}")
        cv2.imwrite(output_path, image)
        return

    # Get all bounding boxes
    boxes = results.boxes.xyxy.cpu().numpy()

    # Filter out very small boxes (e.g., noise)
    img_area = image.shape[0] * image.shape[1]
    min_area = 0.0026 * img_area
    valid_boxes = []
    for box in boxes:
        x1, y1, x2, y2 = box[:4]
        area = (x2 - x1) * (y2 - y1)
        if area >= min_area:
            valid_boxes.append(box)

    if not valid_boxes:
        print(f"Only tiny objects detected in {image_path}, skipping crop")
        cv2.imwrite(output_path, image)
        return

    valid_boxes = np.array(valid_boxes)
    x_min = int(np.min(valid_boxes[:, 0]))
    y_min = int(np.min(valid_boxes[:, 1]))
    x_max = int(np.max(valid_boxes[:, 2]))
    y_max = int(np.max(valid_boxes[:, 3]))

    # Optional: Add margin
    margin = 20
    x_min = max(0, x_min - margin)
    y_min = max(0, y_min - margin)
    x_max = min(image.shape[1], x_max + margin)
    y_max = min(image.shape[0], y_max + margin)

    cropped = image[y_min:y_max, x_min:x_max]
    cv2.imwrite(output_path, cropped)
    print(f"Cropped and saved: {output_path}")

if __name__ == "__main__":
    main()
