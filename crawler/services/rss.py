import feedparser
import time
import urllib.parse

def fetch_rss_data(keywords, base_url):
    """
    Fetch data from RSSHub for given keywords.
    
    Args:
        keywords (list): List of keywords to search.
        base_url (str): Base URL for RSSHub instance.
        
    Returns:
        list: List of dictionaries containing RSS entries.
    """
    results = []
    print("\n📡 [RSS Service] Helper started...")
    
    for kw in keywords:
        # URL Encode the keyword to handle spaces and special chars
        encoded_kw = urllib.parse.quote(kw)
        
        # Example route: Google News via RSSHub
        rss_url = f"{base_url}/google/news/{encoded_kw}"
        
        try:
            feed = feedparser.parse(rss_url)
            if feed.bozo:
                # Often bozo=1 but entries exist, check entries first
                if not feed.entries:
                    print(f"   ⚠️ RSS Parse Error or Empty: {rss_url}")
                    continue
                
            # Get latest 2 entries
            for entry in feed.entries[:2]:
                results.append({
                    "platform": "RSSHub-News",
                    "keyword": kw,
                    "title": entry.title,
                    "url": entry.link,
                    "summary": entry.get('summary', '')[:100]
                })
        except Exception as e:
            print(f"   ⚠️ RSSHub Error ({kw}): {e}")
            
    return results
