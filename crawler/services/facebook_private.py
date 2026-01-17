# crawler/services/facebook_private.py
import os
from facebook_scraper import get_posts
from ..config import FACEBOOK_COOKIES_PATH

def fetch_private_group_posts(group_id, pages=2):
    """
    Fetch posts from a specific Facebook Group (Public or Private).
    Requires 'cookies.txt' (Netscape format) or 'cookies.json' to be set in config.
    
    Args:
        group_id (str): The ID or username of the group. 
                        e.g. "123456789" or "python-developers"
        pages (int): Number of pages to scrape.
    """
    results = []
    print(f"\n👥 [Facebook Private] Starting scrape for Group: {group_id}")
    
    if not FACEBOOK_COOKIES_PATH or not os.path.exists(FACEBOOK_COOKIES_PATH):
        print(f"      ⚠️ Cookies not found at {FACEBOOK_COOKIES_PATH}. Cannot scrape private groups.")
        print("      👉 Please export cookies to 'data/facebook_cookies.txt' using a browser extension (e.g. 'Get cookies.txt LOCALLY').")
        return []

    try:
        # get_posts yields generators
        posts = get_posts(group=group_id, pages=pages, cookies=FACEBOOK_COOKIES_PATH, options={"comments": False})
        
        for post in posts:
            if not post:
                continue
                
            # Extract useful fields
            text = post.get('text', '')[:200].replace('\n', ' ')
            link = post.get('post_url')
            time_ = post.get('time')
            
            # Simple keyword filtering could happen here or in the caller
            # For now, we return everything from the group
            
            results.append({
                "platform": "Facebook-Group",
                "keyword": group_id, # We use group_id as the 'category'
                "title": text, # FB posts often don't have titles, use partial text
                "url": link,
                "summary": f"Posted at {time_}",
            })
            
        print(f"      ✅ [Facebook] Found {len(results)} posts in group {group_id}")
            
    except Exception as e:
        print(f"      ❌ [Facebook] Error: {e}")
        # Common error: Login required, checkpoint, etc.
        
    return results
