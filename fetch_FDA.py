import requests
import json

def fetch_drug_data(generic_name):
    """
    Queries the OpenFDA API for official drug labeling, warnings, and dosages.
    """
    print(f"🌍 Querying US FDA Database for: {generic_name.upper()}...")
    
    # We construct the API URL. We search by generic_name and limit the result to 1.
    url = f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{generic_name}\"&limit=1"
    
    try:
        response = requests.get(url)
        
        # HTTP 200 means the request was successful
        if response.status_code == 200:
            # Parse the massive JSON response
            raw_data = response.json()
            
            # The actual drug info is inside the 'results' array
            drug_info = raw_data['results'][0]
            
            # The FDA JSON is notoriously messy, so we use .get() with fallback strings
            # because not every drug has a boxed warning.
            brand_name = drug_info.get('openfda', {}).get('brand_name', ['Unknown'])[0]
            boxed_warning = drug_info.get('boxed_warning', ['✅ No Black Box Warning for this drug.'])[0]
            indications = drug_info.get('indications_and_usage', ['No indications listed.'])[0]
            dosage_rules = drug_info.get('dosage_and_administration', ['No dosage rules listed.'])[0]
            
            print(f"\n{'='*50}")
            print(f"⚕️  FDA OFFICIAL RECORD: {brand_name.upper()} ({generic_name.title()})")
            print(f"{'='*50}")
            
            print("\n🚨 BOXED WARNING:")
            # We truncate the output so it doesn't flood your entire terminal
            print(f"{boxed_warning[:600]}...\n")
            
            print("📝 INDICATIONS & USAGE:")
            print(f"{indications[:600]}...\n")
            
            print("💊 DOSAGE & ADMINISTRATION:")
            print(f"{dosage_rules[:600]}...\n")
            print(f"{'='*50}")
            
        elif response.status_code == 404:
            print(f"❌ Error: Drug '{generic_name}' not found in the FDA database.")
        else:
            print(f"❌ API Error: HTTP {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network Error: Could not connect to OpenFDA API. {e}")

if __name__ == "__main__":
    # Test it with Linaclotide
    test_drug = "linaclotide"
    fetch_drug_data(test_drug)
    
    # You can also test it with Ibuprofen to see the difference!
    # fetch_drug_data("ibuprofen")