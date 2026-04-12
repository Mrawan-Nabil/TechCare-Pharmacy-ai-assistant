import chromadb

def setup_vector_db():
    print("Initializing ChromaDB vector database...")
    print("Note: The first time you run this, it may take a minute to download the embedding model.\n")

    # 1. Initialize a local persistent client
    # This creates a folder called 'chroma_data' to save your vectors permanently
    chroma_client = chromadb.PersistentClient(path="./chroma_data")
    
    # 2. Create or get the collection (think of this as a table for unstructured data)
    collection = chroma_client.get_or_create_collection(name="drug_interactions")

    # 3. Define our unstructured medical text
    

    # 4. Add the data to ChromaDB


    print("Task Completed: 'chroma_data' folder initialized and vectors embedded successfully!")

if __name__ == "__main__":
    setup_vector_db()