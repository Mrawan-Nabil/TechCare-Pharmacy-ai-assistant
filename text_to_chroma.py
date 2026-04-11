import chromadb

def process_text_to_chromadb(file_path):
    print(f"Reading text file: {file_path}...")
    
    # 1. Read the raw text file
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            extracted_text = file.read()
    except FileNotFoundError:
        print(f"Error: Could not find '{file_path}'")
        return

    # 2. Chunk the text into paragraphs by splitting at double newlines
    raw_paragraphs = extracted_text.split('\n\n')
    clean_paragraphs = [p.strip() for p in raw_paragraphs if len(p.strip()) > 50]
    
    print(f"Extracted {len(clean_paragraphs)} valid medical guidelines. Embedding into ChromaDB...")

    # 3. Connect to ChromaDB
    chroma_client = chromadb.PersistentClient(path="./chroma_data")
    collection = chroma_client.get_or_create_collection(name="drug_interactions")

    # 4. Generate IDs and Metadata
    ids = [f"guideline_chunk_{i}" for i in range(len(clean_paragraphs))]
    metadatas = [{"source": file_path} for _ in clean_paragraphs]

    # 5. Insert into the Vector Database
    collection.add(
        documents=clean_paragraphs,
        metadatas=metadatas,
        ids=ids
    )

    print("Success! Your large text data is now stored in ChromaDB.")

if __name__ == "__main__":
    process_text_to_chromadb("sample.txt")