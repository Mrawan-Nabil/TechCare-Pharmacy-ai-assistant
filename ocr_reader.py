from PIL import Image
import pytesseract
import re
import os

# IMPORTANT: This tells Python exactly where the Tesseract engine is installed.
# If you installed it somewhere else, you MUST update this path!
pytesseract.pytesseract.tesseract_cmd = r'E:\Programs\Tesseract-OCR\tesseract.exe'

def extract_and_sanitize_text(image_path):
    print(f"Scanning prescription image: {image_path}...\n")
    
    if not os.path.exists(image_path):
        print(f"Error: Could not find the image '{image_path}'.")
        print("Please create a test image and place it in the project folder.")
        return None

    try:
        # 1. Open the image file
        img = Image.open(image_path)
        
        # 2. Run OCR to extract the raw text
        raw_text = pytesseract.image_to_string(img)
        clean_text = re.sub(r'[<>/{}[\]~`]', '', raw_text).strip()
        return clean_text
        
    except Exception as e:
        print(f"An error occurred during OCR: {e}")
        return None

if __name__ == "__main__":
    # We are going to test this with a dummy image
    test_image_file = "prescription.png"
    extracted_data = extract_and_sanitize_text(test_image_file)
    
    if extracted_data:
        print(f"✅ Final Sanitized Data Ready for Controller:\n{extracted_data}")