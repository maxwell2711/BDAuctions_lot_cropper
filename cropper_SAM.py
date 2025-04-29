import cv2
import numpy as np
import torch
from segment_anything import sam_model_registry, SamPredictor
import os
import torch.torch_version
from tqdm import tqdm

def main():
    input_dir = "E:\Python Projects\\auto_cropper\BDAuctions_lot_cropper\\test_input"
    output_dir = "E:\Python Projects\\auto_cropper\BDAuctions_lot_cropper\\test_output"
    os.makedirs(output_dir, exist_ok=True)

    sam_predictor = load_sam_predictor()

    print("preparing to run crop")
    print("PyTorch version:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    print("Device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "No GPU")
    for filename in tqdm(os.listdir(input_dir)):
        if filename.lower().endswith((".jpg", ".png", ".jpeg")):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            crop_with_sam(input_path, output_path, sam_predictor)

# Load SAM model
def load_sam_predictor(model_type="vit_h", checkpoint="sam_vit_h_4b8939.pth"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    sam = sam_model_registry[model_type](checkpoint=checkpoint)
    sam.to(device)
    predictor = SamPredictor(sam)
    return predictor

# Main function
def crop_with_sam(image_path, output_path, predictor):
    image = cv2.imread(image_path)
    if image is None:
        print(f"Failed to load image: {image_path}")
        return
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    predictor.set_image(image_rgb)

    height, width = image_rgb.shape[:2]
    point_coords = np.array([[width // 2, height // 2]])
    point_labels = np.array([1])

    try:
        masks, scores, _ = predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            multimask_output=True
        )
    except Exception as e:
        print(f"Mask prediction error for {image_path}: {e}")
        cv2.imwrite(output_path, image)
        return

    if masks is None or masks.shape[0] == 0:
        print("No masks generated")
        cv2.imwrite(output_path, image)
        return

    # Area filter
    image_area = height * width
    min_area = 0.02 * image_area
    max_area = 0.95 * image_area

    candidates = [
        (i, scores[i], np.sum(masks[i]))
        for i in range(len(masks))
        if min_area < np.sum(masks[i]) < max_area
    ]

    if not candidates:
        print(f"No good masks found for {image_path}, saving original")
        cv2.imwrite(output_path, image)
        return

    # Pick highest scoring candidate
    best_index = max(candidates, key=lambda x: x[1])[0]
    best_mask = masks[best_index].astype(np.uint8)

    # Find bounding box
    contours, _ = cv2.findContours(best_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print(f"No contours found for {image_path}, saving original")
        cv2.imwrite(output_path, image)
        return

    x, y, w, h = cv2.boundingRect(np.vstack(contours))

    # Optional: small padding
    pad_pct = 0.05
    pad_x = int(w * pad_pct)
    pad_y = int(h * pad_pct)
    x = max(0, x - pad_x)
    y = max(0, y - pad_y)
    w = min(width - x, w + 2 * pad_x)
    h = min(height - y, h + 2 * pad_y)

    cropped = image[y:y+h, x:x+w]
    cv2.imwrite(output_path, cropped)
    print(f"Cropped and saved: {output_path}")

if __name__ == "__main__":
    main()
