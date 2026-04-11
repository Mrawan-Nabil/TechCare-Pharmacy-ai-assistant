import pandas as pd

# The mix of existing, new, and messy text
data = {
    "generic_name": [
        "ibuprofen",      # Existing
        "amoxicillin",    # Existing
        "azithromycin",   # New
        "LOSARTAN",       # New (Testing uppercase)
        "   metformin   ",# Existing (Testing whitespace)
        "prednisone",     # New
        "citalopram",     # New
        "pantoprazole"    # New
    ]
}

df = pd.DataFrame(data)
df.to_excel("test_batch.xlsx", index=False)
print("✅ test_batch.xlsx created successfully!")