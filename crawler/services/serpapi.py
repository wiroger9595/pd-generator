# crawler/services/serpapi.py
from serpapi import GoogleSearch
import os

# You can set this env var or pass it in
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

def search_serpapi(query, api_key=None):
    """
    Search Google using SerpApi.
    """
    token = api_key or SERPAPI_KEY
    if not token:
        print("   ⚠️ [SerpApi] No API Key found! Please set SERPAPI_KEY.")
        return []

    print(f"   🚀 [SerpApi] Searching: {query}")
    results = []
    
    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": token,
            "num": 5, # Number of results
            "hl": "zh-tw", # Language: Traditional Chinese
            "gl": "tw",    # Region: Taiwan
        }

        search = GoogleSearch(params)
        data = search.get_dict()
        
        # Check for errors in response
        if "error" in data:
             print(f"      ❌ [SerpApi] Error: {data['error']}")
             return []

        organic_results = data.get("organic_results", [])
        
        if organic_results:
             print(f"      ✅ [SerpApi] Found {len(organic_results)} results")
        else:
             print(f"      ⚠️ [SerpApi] No results found")

        for res in organic_results:
            results.append({
                "title": res.get("title"),
                "url": res.get("link"),
                "summary": res.get("snippet"),
            })

    except Exception as e:
        print(f"      ❌ [SerpApi] Request Failed: {e}")
        
    return results
