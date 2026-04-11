import chromadb
import PyPDF2

def process_pdf_to_chromadb(pdf_file_path):
    print(f"Reading PDF: {pdf_file_path}...")
    
    # 1. Open and extract text from the PDF
    extracted_text = ""
    try:
        with open(pdf_file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
    except FileNotFoundError:
        print(f"Error: Could not find the file '{pdf_file_path}'")
        return

    # 2. "Chunk" the text into paragraphs
    # AI embedding models work best with small chunks of text, not massive books.
    # We split the text by double newlines (which usually represent paragraphs)
    raw_paragraphs = extracted_text.split('\n\n')
    
    # Clean up empty lines and ignore tiny fragments (less than 50 characters)
    clean_paragraphs = [p.strip() for p in raw_paragraphs if len(p.strip()) > 50]
    
    if not clean_paragraphs:
        print("No valid text found in the PDF.")
        return

    print(f"Extracted {len(clean_paragraphs)} valid paragraphs. Embedding into ChromaDB...")

    # 3. Connect to ChromaDB
    chroma_client = chromadb.PersistentClient(path="./chroma_data")
    collection = chroma_client.get_or_create_collection(name="drug_interactions")

    # 4. Generate IDs and Metadata for ChromaDB
    # Every piece of text needs a unique ID and a source label
    ids = [f"pdf_chunk_{i}" for i in range(len(clean_paragraphs))]
    metadatas = [{"source": pdf_file_path} for _ in clean_paragraphs]

    # 5. Insert into the Vector Database
    collection.add(
        documents=clean_paragraphs,
        metadatas=metadatas,
        ids=ids
    )

    print("Success! Your PDF data is now stored in ChromaDB as mathematical vectors.")

if __name__ == "__main__":
    # Put a sample medical PDF in your folder and change this name!
    # For now, you can test it with the project PDF you already have.
    sample_pdf = "../BNF-80.pdf" 
    
    process_pdf_to_chromadb(sample_pdf)