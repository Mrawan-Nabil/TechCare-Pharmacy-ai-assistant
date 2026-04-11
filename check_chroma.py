import chromadb

def check_chroma():
    print("🧠 Checking ChromaDB Vector Store (chroma_data)...")
    try:
        chroma_client = chromadb.PersistentClient(path="./chroma_data")
        collection = chroma_client.get_collection(name="drug_interactions")
        
        # Fetch everything in the database
        results = collection.get()
        total_items = len(results['ids'])
        
        if total_items == 0:
            print("⚠️ The ChromaDB collection is currently EMPTY.")
        else:
            print(f"\n✅ Found {total_items} drugs indexed in ChromaDB:\n")
            print("=" * 65)
            
            for i in range(total_items):
                drug_id = results['ids'][i]
                metadata = results['metadatas'][i]
                document = results['documents'][i].replace('\n', ' ') # Clean up line breaks for display
                
                print(f"💊 Drug ID: {drug_id.upper()}")
                print(f"📁 Source: {metadata.get('source', 'Unknown')}")
                print(f"📄 FDA Context Snippet: {document[:150]}...\n")
                
    except Exception as e:
         print(f"❌ ChromaDB Error: {e}\n(The database might not exist yet.)")

if __name__ == "__main__":
    check_chroma()