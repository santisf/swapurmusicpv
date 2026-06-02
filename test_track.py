import urllib.parse
import re

try:
    import requests
except ImportError:
    print("Requests module not found. Skipping DuckDuckGo search simulation.")
    requests = None

title = "Creo"
artist = "Callejeros"

clean_title = re.sub(r"[\(\[][Oo]fficial[\s\w]*[\)\]]", "", title, flags=re.IGNORECASE).strip()
clean_artist = artist.replace(" - Topic", "").strip()
clean_title = re.sub(r"[\(\[].*?[\)\]]", "", clean_title).strip()

queries = [
    f'site:open.spotify.com/track "{clean_artist}" "{clean_title}"',
    f"site:open.spotify.com/track {clean_artist} {clean_title}",
    f"{clean_artist} {clean_title} spotify track"
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

print("Running strategies...")
if requests is not None:
    for q in queries:
        print(f"QUERY: {q}")
        encoded_q = urllib.parse.quote(q)
        url = f"https://html.duckduckgo.com/html/?q={encoded_q}"
        print("URL:", url)
        try:
            res = requests.get(url, headers=headers, timeout=8)
            print("Response code:", res.status_code)
            if res.ok:
                html = res.text
                track_ids = re.findall(r"spotify\.com/(?:[a-zA-Z0-9_-]+/)?track/([a-zA-Z0-9]+)", html)
                print("Track IDs found:", track_ids)
        except Exception as e:
            print("Request failed:", e)
else:
    print("Mock trace: requests is not available, skipping.")
