from PIL import Image
import pytesseract
import cv2
import numpy as np
import re
import os

# IMPORTANT: This tells Python exactly where the Tesseract engine is installed.
# If you installed it somewhere else, you MUST update this path!
pytesseract.pytesseract.tesseract_cmd = r'E:\Programs\Tesseract-OCR\tesseract.exe'

# --- Tesseract Configuration ---
# --oem 3 : Use the best available OCR Engine Mode (LSTM neural net + legacy)
# --psm 3 : Fully automatic page segmentation, but no OSD (best for documents)
TESS_CONFIG = r'--oem 3 --psm 3'


def preprocess_image(image_path):
    """
    Applies an image preprocessing pipeline using OpenCV to improve OCR accuracy.

    Steps:
    1. Load as grayscale (removes color noise)
    2. Apply Gaussian blur to reduce scanner/photo noise
    3. Apply Adaptive Thresholding to produce a clean binary (black/white) image.
       This handles uneven lighting — a major problem with phone photos of prescriptions.
    """
    # 1. Load image in grayscale
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    if image is None:
        return None

    # 2. Apply Gaussian blur to smooth out noise before thresholding
    image = cv2.GaussianBlur(image, (3, 3), 0)

    # 3. Adaptive Thresholding: converts the image to pure black & white.
    #    Uses local neighbourhood (blockSize=31) to handle uneven lighting across the image.
    #    The constant C=2 is subtracted from the mean — fine-tune if results are too dark/light.
    image = cv2.adaptiveThreshold(
        image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2
    )

    return image


def extract_and_sanitize_text(image_path):
    """
    Main OCR function. Preprocesses the image, then runs Tesseract OCR.
    Returns cleaned text, or None on failure.
    """
    print(f"Scanning prescription image: {image_path}...\n")

    if not os.path.exists(image_path):
        print(f"Error: Could not find the image '{image_path}'.")
        print("Please create a test image and place it in the project folder.")
        return None

    try:
        # 1. Preprocess the image with OpenCV (Grayscale + Blur + Adaptive Threshold)
        processed_cv_image = preprocess_image(image_path)

        if processed_cv_image is None:
            # Fallback: If OpenCV fails (e.g., unsupported format), use PIL directly
            print("Warning: OpenCV preprocessing failed. Falling back to raw PIL image.")
            img = Image.open(image_path)
        else:
            # 2. Convert the OpenCV NumPy array back to a PIL Image for pytesseract
            img = Image.fromarray(processed_cv_image)

        # 3. Run OCR with optimised Tesseract configuration
        raw_text = pytesseract.image_to_string(img, lang='eng', config=TESS_CONFIG)

        # 4. Sanitize the output — remove characters that break JSON/LLM parsing
        clean_text = re.sub(r'[<>/{}[\]~`]', '', raw_text).strip()
        return clean_text

    except Exception as e:
        print(f"An error occurred during OCR: {e}")
        return None


def extract_text(image_path):
    """Reads an image, cleans it mathematically, and extracts text."""

    # 1. Read the image using OpenCV
    img = cv2.imread(image_path)

    # 2. Upscale the image by 2x (Crucial for Tesseract to read tables accurately)
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # 3. Convert to grayscale (Removes color artifacts)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 4. Apply a slight Gaussian blur (Smooths out pixel noise causing those weird symbols)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)

    # 5. Otsu's Thresholding (Forces every pixel to be pure black or pure white)
    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    # 6. Custom Tesseract Configuration
    # --oem 3 uses the standard AI engine.
    # --psm 6 tells Tesseract to assume a single uniform block of text.
    custom_config = r'--oem 3 --psm 6'

    # 7. Extract the text from the CLEANED image, not the raw one
    extracted_text = pytesseract.image_to_string(thresh, config=custom_config)

    return extracted_text


if __name__ == "__main__":

    # Test with the sample prescription image
    test_image_file = "prescription.png"
    extracted_data = extract_and_sanitize_text(test_image_file)

    if extracted_data:
        print(f"✅ Final Sanitized Data Ready for Controller:\n{extracted_data}")