# crawler/services/ddg.py
from duckduckgo_search import DDGS
import time
import random

def search_ddg(query, max_results=3):
    """
    Performs a DuckDuckGo search.
    Returns a list of dicts with title, href, body.
    """
    results = []
    print(f"   🦆 [DDG Fallback] Searching: {query}")
    
    try:
        with DDGS() as ddgs:
            # text search
            ddg_results = ddgs.text(query, max_results=max_results)
            
            for res in ddg_results:
                results.append({
                    "title": res.get("title"),
                    "url": res.get("href"),
                    "summary": res.get("body"),
                })
                
        if results:
             print(f"      ✅ [DDG] Found {len(results)} results")
        else:
             print(f"      ⚠️ [DDG] No results found")
             
    except Exception as e:
        print(f"      ❌ [DDG] Error: {e}")
        
    # Small sleep is polite even for DDG
    time.sleep(random.uniform(2, 5))
    return results
