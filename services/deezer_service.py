import re
import requests

class DeezerService:
    def __init__(self):
        pass

    def is_configured(self):
        # Deezer's public API does not require credentials
        return True

    def resolve_shortened_url(self, url):
        # Solves shortened link like https://deezer.page.link/xyz through redirect scraping
        if "deezer.page.link" in url or "link.deezer.com" in url:
            try:
                res = requests.head(url, allow_redirects=True, timeout=5)
                return res.url
            except Exception as e:
                try:
                    # Fallback standard GET if HEAD is not allowed
                    res2 = requests.get(url, allow_redirects=True, timeout=5)
                    return res2.url
                except Exception as e2:
                    print(f"Error resolving Deezer shortened URL: {e2}")
        return url

    def extract_id(self, url):
        url = self.resolve_shortened_url(url)
        
        # Matches patterns like deezer.com/track/123 or deezer.com/en/track/123
        track_match = re.search(r"deezer\.com/(?:[a-zA-Z]{2}/)?track/(\d+)", url)
        if track_match:
            return "track", track_match.group(1)
            
        playlist_match = re.search(r"deezer\.com/(?:[a-zA-Z]{2}/)?playlist/(\d+)", url)
        if playlist_match:
            return "playlist", playlist_match.group(1)
            
        return None, None

    def get_track_details(self, track_id):
        try:
            api_url = f"https://api.deezer.com/track/{track_id}"
            res = requests.get(api_url, timeout=10)
            res.raise_for_status()
            data = res.json()
            
            if "error" in data:
                raise Exception(data["error"].get("message", "Unknown Deezer API error"))
                
            return {
                "title": data["title"],
                "artist": data["artist"]["name"],
                "url": f"https://www.deezer.com/track/{track_id}"
            }
        except Exception as e:
            raise Exception(f"Failed to fetch Deezer track detail: {e}")

    def get_playlist_tracks(self, playlist_id):
        try:
            api_url = f"https://api.deezer.com/playlist/{playlist_id}"
            res = requests.get(api_url, timeout=10)
            res.raise_for_status()
            data = res.json()
            
            if "error" in data:
                raise Exception(data["error"].get("message", "Unknown Deezer API error"))
                
            tracks_data = []
            tracks_list = data.get("tracks", {}).get("data", [])
            
            for item in tracks_list:
                tracks_data.append({
                    "title": item["title"],
                    "artist": item["artist"]["name"],
                    "url": f"https://www.deezer.com/track/{item['id']}"
                })
                
            # Handle list pagination if present (Deezer embeds up to 400 tracks or lists 'next' URL)
            next_url = data.get("tracks", {}).get("next")
            while next_url and len(tracks_data) < 200:
                res = requests.get(next_url, timeout=10)
                res.raise_for_status()
                next_data = res.json()
                for item in next_data.get("data", []):
                    tracks_data.append({
                        "title": item["title"],
                        "artist": item["artist"]["name"],
                        "url": f"https://www.deezer.com/track/{item['id']}"
                    })
                next_url = next_data.get("next")
                
            return tracks_data
        except Exception as e:
            raise Exception(f"Failed to fetch Deezer playlist tracks: {e}")

    def search_track(self, title, artist):
        try:
            clean_title = re.sub(r"[\(\[][Oo]fficial[\s\w]*[\)\]]", "", title, flags=re.IGNORECASE).strip()
            clean_artist = artist.replace(" - Topic", "").strip()
            
            # Split artists to find primary and others (handles feat., ampersands, commas)
            artists_list = [s.strip() for s in re.split(r"[,&]|\bfeat\.?\b|\band\b", clean_artist, flags=re.IGNORECASE) if s.strip()]
            primary_artist = artists_list[0] if artists_list else ""
            
            strategies = []
            if primary_artist:
                strategies.append(f'track:"{clean_title}" artist:"{primary_artist}"')
            if clean_artist and clean_artist != primary_artist:
                strategies.append(f'track:"{clean_title}" artist:"{clean_artist}"')
            if primary_artist:
                strategies.append(f"{primary_artist} {clean_title}")
            if artists_list:
                strategies.append(f'{" ".join(artists_list)} {clean_title}')
            strategies.append(clean_title)
            
            items = []
            for query in strategies:
                if not query:
                    continue
                api_url = f"https://api.deezer.com/search?q={requests.utils.quote(query)}"
                try:
                    res = requests.get(api_url, timeout=10)
                    if res.ok:
                        data = res.json()
                        results = data.get("data", [])
                        if results:
                            items = results
                            break # Found successful strategy!
                except Exception as e_strat:
                    print(f"Deezer strategy failed for '{query}': {e_strat}")
                    
            candidates = []
            for item in items[:5]: # Top 5 results
                candidates.append({
                    "title": item["title"],
                    "artist": item["artist"]["name"],
                    "url": f"https://www.deezer.com/track/{item['id']}"
                })
            return candidates
        except Exception as e:
            print(f"Deezer search error: {e}")
            return []
