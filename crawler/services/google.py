# crawler/services/google.py
from googlesearch import search
import time
import random
from fake_useragent import UserAgent
from .ddg import search_ddg
from .serpapi import search_serpapi
from ..config import SERPAPI_KEY

def fetch_google_data(keywords, social_platforms=None):
    """
    Fetch data from Google Search (SerpApi -> Google Web -> DuckDuckGo).
    """
    results = []
    print("\n🔍 [Search Service] Helper started (SerpApi -> Google -> DDG)...", flush=True)
    
    # ... (rest of the function setup)
    
    # Randomize User-Agent
    ua = UserAgent()

    # Consolidate all queries
    all_queries = []
    
    # 1. Google Web
    for kw in keywords:
        all_queries.append({
            "source": "Web",
            "keyword": kw,
            "query": kw
        })
        
    # 2. Social Platforms
    if social_platforms:
        for platform, site_prefix in social_platforms.items():
            for kw in keywords:
                query = f'{site_prefix} "{kw}"'
                all_queries.append({
                    "source": f"{platform.capitalize()}",
                    "keyword": kw,
                    "query": query
                })
    
    # Shuffle
    random.shuffle(all_queries)
    
    # Process queries
    for params in all_queries:
        query_results = []
        _perform_search_with_fallback(params, query_results, ua.random)
        
        # Log immediately after each query to show progress in file
        if query_results:
            from ..utils.file_logger import log_results_to_file
            log_results_to_file(query_results)
            results.extend(query_results)
        
        # Slower sleep is still good practice, but SerpApi is faster
        sleep_time = random.uniform(5, 10) 
        print(f"      💤 Sleeping for {sleep_time:.1f}s...", flush=True)
        time.sleep(sleep_time)
                
    return results

def _perform_search_with_fallback(params, results_list, user_agent):
    query = params["query"]
    print(f"   -> Searching: {query}", flush=True)
    
    # --- 1. Try SerpApi First (Most Reliable) ---
    if SERPAPI_KEY and "YOUR_API_KEY" not in SERPAPI_KEY:
        try:
            serp_results = search_serpapi(query, SERPAPI_KEY)
            if serp_results:
                for res in serp_results:
                    results_list.append({
                        "platform": f"SerpApi-{params['source']}",
                        "keyword": params["keyword"],
                        "title": res['title'],
                        "url": res['url'],
                        "summary": res['summary']
                    })
                return True
        except Exception as e:
            print(f"   ⚠️ [SerpApi] Skipped/Failed: {e}", flush=True)
    
    # --- 2. Try Google Direct (Free but Block-prone) ---
    try:
        # ... (rest of google logic)
        # google search
        search_results = search(query, num_results=3, advanced=True, sleep_interval=10)
        search_results_list = list(search_results)
        
        if search_results_list:
             print(f"      ✅ [Google] Found {len(search_results_list)} results")
        else:
             print(f"      ⚠️ [Google] No results found")

        for res in search_results_list:
            results_list.append({
                "platform": f"Google-{params['source']}",
                "keyword": params["keyword"],
                "title": res.title,
                "url": res.url,
                "summary": res.description
            })
        return True
        
    except Exception as e:
        print(f"   ⚠️ [Google] Failed/Blocked: {e}", flush=True)
        print("   twisted_rightwards_arrows Switching to DuckDuckGo Fallback...", flush=True)
        
        # --- Fallback to DuckDuckGo ---
        try:
            ddg_results = search_ddg(query)
            for res in ddg_results:
                results_list.append({
                    "platform": f"DDG-{params['source']}",
                    "keyword": params["keyword"],
                    "title": res['title'],
                    "url": res['url'],
                    "summary": res['summary']
                })
            return True
        except Exception as ddg_e:
            print(f"      ❌ [DDG] Fallback also failed: {ddg_e}", flush=True)
            return False
