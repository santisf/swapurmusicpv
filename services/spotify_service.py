import os
import re
import json
import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

class SpotifyService:
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.sp = None
        
        if self.client_id and self.client_secret:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=self.client_id,
                    client_secret=self.client_secret
                )
                self.sp = spotipy.Spotify(auth_manager=auth_manager)
            except Exception as e:
                print(f"Spotify authentication failed: {e}")

    def is_configured(self):
        return self.sp is not None

    def extract_id(self, url):
        # Handle track e.g. https://open.spotify.com/intl-es/track/1TqHcm3i8yDL9XPHXe1oQg?si=...
        track_match = re.search(r"spotify\.com/track/([a-zA-Z0-9]+)", url)
        if track_match:
            return "track", track_match.group(1)
            
        playlist_match = re.search(r"spotify\.com/playlist/([a-zA-Z0-9]+)", url)
        if playlist_match:
            return "playlist", playlist_match.group(1)
            
        return None, None

    def parse_song_and_artist_from_title(self, title_text, oembed_author=None):
        title = title_text.strip()
        artist = oembed_author.strip() if oembed_author else "Unknown Artist"
        
        # Case 1: Has hyphen + song/cancion + by/de, e.g. "Bodybag - canción de Lil Lotus, Cold Hart"
        hyphen_by_match = re.search(r"^(.*?)\s*-\s*(?:song|canción|cancion|track)?\s*(?:by|de)\s+(.+)$", title, re.IGNORECASE)
        if hyphen_by_match:
            title = hyphen_by_match.group(1).strip()
            artist = hyphen_by_match.group(2).strip()
        else:
            # Case 2: No hyphen but has song/cancion/by/de
            last_by_idx = title.lower().rfind(" by ")
            last_de_idx = title.lower().rfind(" de ")
            idx = max(last_by_idx, last_de_idx)
            if idx != -1:
                possible_artist = title[idx + 4:].strip()
                possible_title = title[:idx].strip()
                cleaned_title = re.sub(r"\s*-\s*(?:song|canción|cancion|lyrics|single|ep|track|video|audio)\s*$", "", possible_title, flags=re.IGNORECASE).strip()
                title = cleaned_title
                artist = possible_artist
            elif " - " in title:
                parts = title.split(" - ")
                if oembed_author and oembed_author.lower() in parts[0].lower():
                    artist = parts[0].strip()
                    title = parts[1].strip()
                elif oembed_author and oembed_author.lower() in parts[1].lower():
                    title = parts[0].strip()
                    artist = parts[1].strip()
                else:
                    artist = parts[0].strip()
                    title = parts[1].strip()
        
        artist = re.sub(r" - Topic$", "", artist, flags=re.IGNORECASE).strip()
        title = re.sub(r"[\(\[][Oo]fficial[\s\w]*[\)\]]", "", title, flags=re.IGNORECASE).strip()
        return {"title": title, "artist": artist}

    def public_get_track_details(self, track_id):
        # Fallback 1: Direct HTML page scraping using Googlebot User-Agent.
        try:
            track_url = f"https://open.spotify.com/track/{track_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Accept-Language": "en-US,en;q=0.9"
            }
            res = requests.get(track_url, headers=headers, timeout=10)
            if res.ok:
                html = res.text
                title_match = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE) or \
                              re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:title["\']', html, re.IGNORECASE)
                
                desc_match = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE) or \
                             re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:description["\']', html, re.IGNORECASE)
                
                title = ""
                artist = ""
                
                if title_match:
                    raw_og_title = title_match.group(1).strip()
                    raw_og_title = re.sub(r"\s*\|\s*Spotify", "", raw_og_title, flags=re.IGNORECASE)
                    raw_og_title = re.sub(r"\s*-\s*Spotify", "", raw_og_title, flags=re.IGNORECASE).strip()
                    parsed_og = self.parse_song_and_artist_from_title(raw_og_title)
                    title = parsed_og["title"]
                    artist = parsed_og["artist"] if parsed_og["artist"] != "Unknown Artist" else ""
                
                if desc_match:
                    desc = desc_match.group(1).strip()
                    spotify_idx = desc.lower().find("spotify.")
                    if spotify_idx != -1:
                        desc = desc[spotify_idx + 8:].strip()
                    
                    parts = re.split(r"\s*·\s*", desc)
                    if parts and parts[0].strip():
                        possible_artist = parts[0].strip()
                        if not artist or artist == "Unknown Artist":
                            artist = possible_artist
                
                page_title_match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
                if page_title_match:
                    p_title = page_title_match.group(1).strip()
                    p_title = re.sub(r"\s*\|\s*Spotify", "", p_title, flags=re.IGNORECASE)
                    p_title = re.sub(r"\s*-\s*Spotify", "", p_title, flags=re.IGNORECASE).strip()
                    parsed_meta = self.parse_song_and_artist_from_title(p_title, artist)
                    if not title:
                        title = parsed_meta["title"]
                    if not artist or artist == "Unknown Artist":
                        artist = parsed_meta["artist"]
                
                if title and artist and artist != "Unknown Artist":
                    return {
                        "title": title,
                        "artist": artist,
                        "url": track_url
                    }
        except Exception as e:
            print(f"Direct Spotify scraper fallback failed: {e}")

        # Fallback 2: Official OEmbed API
        try:
            oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
            res = requests.get(oembed_url, timeout=10)
            if res.ok:
                odata = res.json()
                if odata.get("title"):
                    parsed_meta = self.parse_song_and_artist_from_title(odata["title"], odata.get("author_name"))
                    return {
                        "title": parsed_meta["title"],
                        "artist": parsed_meta["artist"],
                        "url": f"https://open.spotify.com/track/{track_id}"
                    }
        except Exception as e:
            print(f"Spotify oEmbed fallback failed: {e}")

        raise Exception("Could not fetch Spotify track details publicly and Spotify API is not configured.")

    def get_track_details(self, track_id):
        if not self.sp:
            return self.public_get_track_details(track_id)
        try:
            track = self.sp.track(track_id)
            return {
                "title": track["name"],
                "artist": ", ".join([artist["name"] for artist in track["artists"]]),
                "url": f"https://open.spotify.com/track/{track_id}"
            }
        except Exception as e:
            # Fallback to public if API fails
            print(f"Spotify API track match failed, falling back to public lookup: {e}")
            return self.public_get_track_details(track_id)

    def get_playlist_tracks(self, playlist_id):
        if not self.sp:
            raise Exception("Spotify Playlist resolution requires Spotify API Configuration (SPOTIFY_CLIENT_ID & SPOTIFY_CLIENT_SECRET) in Streamlit settings.")
        try:
            tracks_data = []
            results = self.sp.playlist_items(playlist_id)
            while results:
                for item in results["items"]:
                    track = item.get("track")
                    if track:
                        tracks_data.append({
                            "title": track["name"],
                            "artist": ", ".join([artist["name"] for artist in track["artists"]]),
                            "url": f"https://open.spotify.com/track/{track['id']}" if track.get('id') else ""
                        })
                if results["next"]:
                    results = self.sp.next(results)
                else:
                    break
            return tracks_data
        except Exception as e:
            raise Exception(f"Failed to fetch Spotify playlist: {e}")

    def search_track(self, title, artist):
        if not self.sp:
            return []
        try:
            clean_title = re.sub(r"[\(\[][Oo]fficial[\s\w]*[\)\]]", "", title, flags=re.IGNORECASE).strip()
            clean_artist = artist.replace(" - Topic", "").strip()
            
            artists_list = [s.strip() for s in re.split(r"[,&]|\bfeat\.?\b|\band\b", clean_artist) if s.strip()]
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
            
            tracks = []
            for query in strategies:
                try:
                    results = self.sp.search(q=query, type="track", limit=5)
                    items = results.get("tracks", {}).get("items", [])
                    if items:
                        tracks = items
                        break
                except Exception as ex:
                    print(f"Spotify strategy search failed: {ex}")
                    
            candidates = []
            for track in tracks:
                candidates.append({
                    "title": track["name"],
                    "artist": ", ".join([a["name"] for a in track["artists"]]),
                    "url": f"https://open.spotify.com/track/{track['id']}"
                })
            return candidates
        except Exception as e:
            print(f"Spotify track search error: {e}")
            return []
