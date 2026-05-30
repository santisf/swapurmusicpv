import os
import re
import json
import requests
import urllib.parse
from googleapiclient.discovery import build

class YouTubeService:
    def __init__(self):
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.yt = None
        
        # Try ADC (Application Default Credentials) first
        try:
            self.yt = build("youtube", "v3")
        except Exception as adc_err:
            print(f"YouTube client with ADC failed or unavailable: {adc_err}. Falling back to developerKey...")
            if self.api_key:
                try:
                    self.yt = build("youtube", "v3", developerKey=self.api_key)
                except Exception as e:
                    print(f"YouTube client initialization with key failed: {e}")

    def is_configured(self):
        # We return True because we support both Authenticated APIs and elegant Public Scraper Fallbacks!
        return True

    def extract_id(self, url):
        # Handle video matching patterns
        # e.g., https://www.youtube.com/watch?v=dQw4w9WgXcQ
        # e.g., https://youtu.be/dQw4w9WgXcQ
        # e.g., https://music.youtube.com/watch?v=dQw4w9WgXcQ
        video_id = None
        playlist_id = None
        
        # Check standard watch, music watch
        watch_match = re.search(r"(?:youtube\.com|music\.youtube\.com)/watch\?v=([a-zA-Z0-9_-]+)", url)
        if watch_match:
            video_id = watch_match.group(1)
        else:
            short_match = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", url)
            if short_match:
                video_id = short_match.group(1)
                
        # Check playlist
        playlist_match = re.search(r"list=([a-zA-Z0-9_-]+)", url)
        if playlist_match:
            playlist_id = playlist_match.group(1)
            
        if playlist_id:
            if "playlist" in url or not video_id:
                return "playlist", playlist_id
            return "track", video_id
            
        if video_id:
            return "track", video_id
            
        return None, None

    def clean_title(self, title):
        if not title:
            return "", ""
        clean_name = re.sub(r'[\(\[][Oo]fficial\s*[Mm]usic\s*[Vv]ideo[\)\]]', '', title)
        clean_name = re.sub(r'[\(\[][Oo]fficial\s*[Vv]ideo[\)\]]', '', clean_name)
        clean_name = re.sub(r'[\(\[][Mm]usic\s*[Vv]ideo[\)\]]', '', clean_name)
        clean_name = re.sub(r'[\(\[][Vv]ideo\s*[Cc]lip[\)\]]', '', clean_name)
        clean_name = re.sub(r'[\(\[][Aa]udio[\)\]]', '', clean_name)
        clean_name = re.sub(r'[\(\[][Ll]yrics[\)\]]', '', clean_name)
        clean_name = re.sub(r'[\(\[][Rr][Ee][Mm][Aa][Ss][Tt][Ee][Rr][Ee][Dd][\)\]]', '', clean_name)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        
        if " - " in clean_name:
            parts = clean_name.split(" - ", 1)
            return parts[1].strip(), parts[0].strip()
        return clean_name, "Unknown Artist"

    def public_get_track_details(self, video_id):
        # 1. oEmbed API Fallback is 100% public, super fast, and requires 0 credentials
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            res = requests.get(oembed_url, timeout=10)
            if res.ok:
                odata = res.json()
                title = odata.get("title", "")
                author = odata.get("author_name", "")
                parsed_title, artist = self.clean_title(title)
                if artist == "Unknown Artist":
                    artist = author.replace(" - Topic", "")
                return {
                    "title": parsed_title,
                    "artist": artist,
                    "url": f"https://music.youtube.com/watch?v={video_id}"
                }
        except Exception as e:
            print(f"YouTube public oEmbed failed: {e}")

        # 2. Scrape watch page using lightweight requests if oEmbed failed
        try:
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
            res = requests.get(watch_url, headers=headers, timeout=10)
            if res.ok:
                html = res.text
                title_match = re.search(r'<meta\s+name=["\']title["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE) or \
                              re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
                if title_match:
                    raw_title = title_match.group(1).replace(" - YouTube", "").strip()
                    parsed_title, artist = self.clean_title(raw_title)
                    return {
                        "title": parsed_title,
                        "artist": artist,
                        "url": f"https://music.youtube.com/watch?v={video_id}"
                    }
        except Exception as e:
            print(f"YouTube watch scraper failed: {e}")

        raise Exception("Could not fetch YouTube/YouTube Music details publicly.")

    def get_track_details(self, video_id):
        if not self.yt:
            return self.public_get_track_details(video_id)
        try:
            req = self.yt.videos().list(
                part="snippet",
                id=video_id
            )
            res = req.execute()
            items = res.get("items", [])
            if not items:
                return self.public_get_track_details(video_id)
                
            snippet = items[0]["snippet"]
            title = snippet["title"]
            channel_title = snippet["channelTitle"]
            
            parsed_title, artist = self.clean_title(title)
            if artist == "Unknown Artist":
                artist = channel_title.replace(" - Topic", "")
                
            return {
                "title": parsed_title,
                "artist": artist,
                "url": f"https://music.youtube.com/watch?v={video_id}"
            }
        except Exception as e:
            print(f"YouTube API failed to fetch details, falling back: {e}")
            return self.public_get_track_details(video_id)

    def public_get_playlist_tracks(self, playlist_id):
        try:
            url = f"https://www.youtube.com/playlist?list={playlist_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
            res = requests.get(url, headers=headers, timeout=10)
            if not res.ok:
                raise Exception(f"HTTP request failed with status {res.status_code}")
                
            html = res.text
            # Extract videoRenderer items embedded in ytInitialData inside script blocks
            video_sections = re.findall(
                r'\{"playlistVideoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"([^"]+)"\}\].*?"shortBylineText":\{"runs":\[\{"text":"([^"]+)"\}', 
                html
            )
            
            tracks_data = []
            seen_ids = set()
            for vid, title, channel in video_sections:
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)
                parsed_title, artist = self.clean_title(title)
                if artist == "Unknown Artist":
                    artist = channel.replace(" - Topic", "")
                tracks_data.append({
                    "title": parsed_title,
                    "artist": artist,
                    "url": f"https://music.youtube.com/watch?v={vid}"
                })
                
            # If standard regex did not match, do simple regex extraction
            if not tracks_data:
                simple_vids = re.findall(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html)
                unique_vids = []
                for v in simple_vids:
                    if v not in seen_ids and len(unique_vids) < 30:
                        seen_ids.add(v)
                        unique_vids.append(v)
                        
                for vid in unique_vids:
                    try:
                        tr_details = self.public_get_track_details(vid)
                        tracks_data.append(tr_details)
                    except:
                        pass
                        
            if not tracks_data:
                raise Exception("Could not find any playlist track list via public scraping.")
                
            return tracks_data
        except Exception as e:
            raise Exception(f"Failed to fetch public YouTube playlist tracks: {e}")

    def get_playlist_tracks(self, playlist_id):
        if not self.yt:
            return self.public_get_playlist_tracks(playlist_id)
        try:
            tracks_data = []
            next_page_token = None
            
            while True:
                req = self.yt.playlistItems().list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                res = req.execute()
                items = res.get("items", [])
                
                for item in items:
                    snippet = item.get("snippet", {})
                    title = snippet.get("title", "")
                    video_id = snippet.get("resourceId", {}).get("videoId", "")
                    channel_title = snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or "Unknown"
                    
                    if video_id:
                        parsed_title, artist = self.clean_title(title)
                        if artist == "Unknown Artist":
                            artist = channel_title.replace(" - Topic", "")
                        tracks_data.append({
                            "title": parsed_title,
                            "artist": artist,
                            "url": f"https://music.youtube.com/watch?v={video_id}"
                        })
                        
                next_page_token = res.get("nextPageToken")
                if not next_page_token or len(tracks_data) >= 150:
                    break
                    
            return tracks_data
        except Exception as e:
            print(f"YouTube API playlist retrieval failed, trying public scraping fallback: {e}")
            return self.public_get_playlist_tracks(playlist_id)

    def public_search_track(self, title, artist):
        try:
            query = f"{artist} {title}"
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.youtube.com/results?search_query={encoded_query}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
            res = requests.get(url, headers=headers, timeout=10)
            if not res.ok:
                return []
                
            html = res.text
            # Identify videoRenderer elements
            video_matches = re.findall(
                r'"videoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"([^"]+)"\}\].*?"ownerText":\{"runs":\[\{"text":"([^"]+)"\}', 
                html
            )
            
            candidates = []
            seen_ids = set()
            for vid, v_title, channel in video_matches:
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)
                parsed_title, v_artist = self.clean_title(v_title)
                if v_artist == "Unknown Artist":
                    v_artist = channel.replace(" - Topic", "")
                candidates.append({
                    "title": parsed_title,
                    "artist": v_artist,
                    "url": f"https://music.youtube.com/watch?v={vid}"
                })
                if len(candidates) >= 5:
                    break
                    
            # Simpler regex fallback if structured extraction misses items
            if not candidates:
                video_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html)
                unique_ids = []
                for vid in video_ids:
                    if vid not in seen_ids:
                        seen_ids.add(vid)
                        unique_ids.append(vid)
                        
                for vid in unique_ids[:3]:
                    try:
                        det = self.public_get_track_details(vid)
                        candidates.append(det)
                    except:
                        pass
            return candidates
        except Exception as e:
            print(f"YouTube public search error: {e}")
            return []

    def search_track(self, title, artist):
        if not self.yt:
            return self.public_search_track(title, artist)
        try:
            query = f"{artist} {title}"
            req = self.yt.search().list(
                q=query,
                part="snippet",
                maxResults=5,
                type="video"
            )
            res = req.execute()
            items = res.get("items", [])
            
            candidates = []
            for item in items:
                video_id = item["id"].get("videoId")
                if video_id:
                    v_title = item["snippet"]["title"]
                    channel_title = item["snippet"]["channelTitle"]
                    parsed_title, v_artist = self.clean_title(v_title)
                    if v_artist == "Unknown Artist":
                        v_artist = channel_title.replace(" - Topic", "")
                    candidates.append({
                        "title": parsed_title,
                        "artist": v_artist,
                        "url": f"https://music.youtube.com/watch?v={video_id}"
                    })
            if not candidates:
                return self.public_search_track(title, artist)
            return candidates
        except Exception as e:
            print(f"YouTube API search failed, fallback to scraper: {e}")
            return self.public_search_track(title, artist)
