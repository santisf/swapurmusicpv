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
        
        if self.api_key:
            try:
                self.yt = build("youtube", "v3", developerKey=self.api_key)
                print("YouTube client initialized with developerKey.")
            except Exception as e:
                print(f"YouTube client initialization with key failed: {e}")
        else:
            # Try ADC (Application Default Credentials) only if no API key is specified
            try:
                self.yt = build("youtube", "v3")
                print("YouTube client initialized with ADC.")
            except Exception as adc_err:
                print(f"YouTube client with ADC failed or unavailable: {adc_err}")

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
        # Strip common metadata/video tags found in brackets or parentheses
        clean_name = re.sub(
            r'[\(\[][^\)\]]*(?:video|audio|official|music|clip|hd|definition|remastered|remaster|lyrics?|version|live|acoustic)[^\)\]]*[\)\]]', 
            '', 
            title, 
            flags=re.IGNORECASE
        )
        clean_name = re.sub(r'\(\s*\)|\[\s*\]', '', clean_name)
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
        import traceback
        import subprocess
        debug_info = []
        tracks_data = []
        seen_ids = set()
        fetched_htmls = []

        # 1. Try public XML/RSS feed first (extremely reliable, lightweight, and bypasses JS-rendering / scrapers block)
        try:
            import urllib.request
            import xml.etree.ElementTree as ET
            debug_info.append(f"Attempting RSS/XML feed fetch for playlist: {playlist_id}")
            rss_url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"
            
            # Fetch XML data using urllib
            req = urllib.request.Request(rss_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()
                
            debug_info.append(f"RSS/XML fetch succeeded (len: {len(xml_data)})")
            
            # Parse XML
            root = ET.fromstring(xml_data)
            
            # Namespaces used in YouTube Atom feeds
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'yt': 'http://www.youtube.com/xml/schemas/2015'
            }
            
            xml_tracks = []
            for entry in root.findall('atom:entry', ns) or root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                title_elem = entry.find('atom:title', ns) or entry.find('.//{http://www.w3.org/2005/Atom}title')
                video_id_elem = entry.find('yt:videoId', ns) or entry.find('.//{http://www.youtube.com/xml/schemas/2015}videoId')
                author_elem = entry.find('atom:author/atom:name', ns) or entry.find('.//{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name')
                
                title = title_elem.text if title_elem is not None else ""
                video_id = video_id_elem.text if video_id_elem is not None else ""
                author = author_elem.text if author_elem is not None else ""
                
                if video_id and title:
                    parsed_title, artist = self.clean_title(title)
                    if artist == "Unknown Artist" and author:
                        artist = author.replace(" - Topic", "")
                    
                    xml_tracks.append({
                        "title": parsed_title,
                        "artist": artist,
                        "url": f"https://music.youtube.com/watch?v={video_id}"
                    })
                    seen_ids.add(video_id)
            
            if xml_tracks:
                debug_info.append(f"Successfully retrieved {len(xml_tracks)} tracks from RSS feed!")
                return xml_tracks
                
        except Exception as rss_err:
            debug_info.append(f"RSS/XML feed fetch failed: {rss_err}")

        # Try both youtube.com and music.youtube.com domains for broader scraper resilience
        urls_to_try = [
            f"https://www.youtube.com/playlist?list={playlist_id}",
            f"https://music.youtube.com/playlist?list={playlist_id}"
        ]

        # Use robust, universal custom headers to completely bypass YouTube's GDPR/cookie-consent walls
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": "CONSENT=YES+cb.20210328-17-p0.en-GB+FX+999; SOCS=eSG_AgIE"
        }

        # Subprocess curl-based, requests-based, and urllib-based fetch strategy
        def try_fetch_html(url):
            # 1) Try standard urllib first (extremely reliable on Cloud Run and bypasses proxy block)
            try:
                import urllib.request
                debug_info.append(f"Attempting urllib fetch on: {url}")
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    html = response.read().decode('utf-8', errors='ignore')
                if html and len(html) > 30000:
                    debug_info.append(f"Urllib fetch succeeded (len: {len(html)})")
                    return html
                else:
                    debug_info.append(f"Urllib returned short response (len: {len(html) if html else 0})")
            except Exception as e:
                debug_info.append(f"Urllib fetch failed: {e}")

            # 2) Try standard requests as fallback
            try:
                debug_info.append(f"Attempting requests fetch on: {url}")
                res = requests.get(url, headers=headers, timeout=10)
                if res.ok and len(res.text) > 30000:
                    debug_info.append(f"Requests fetch succeeded with status {res.status_code}")
                    return res.text
                else:
                    debug_info.append(f"Requests fetch returned non-ideal response (status: {res.status_code}, len: {len(res.text) if res.text else 0})")
            except Exception as e:
                debug_info.append(f"Requests fetch failed: {e}")

            # 3) Fallback to subprocess curl call (bypasses most bot shields, highly reliable on Cloud Run)
            try:
                debug_info.append("Initiating curl subprocess fallback fetch...")
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
                accept_lang = "en-US,en;q=0.9"
                cookie = "CONSENT=YES+cb.20210328-17-p0.en-GB+FX+999; SOCS=eSG_AgIE"
                
                command = [
                    "curl", "-sL", "--max-time", "15",
                    "-H", f"User-Agent: {user_agent}",
                    "-H", f"Accept-Language: {accept_lang}",
                    "-b", cookie,
                    url
                ]
                html_bytes = subprocess.check_output(command, stderr=subprocess.DEVNULL, timeout=15)
                html = html_bytes.decode('utf-8', errors='ignore')
                if html and len(html) > 30000:
                    debug_info.append(f"Curl subprocess fallback succeeded (len: {len(html)})")
                    return html
                else:
                    debug_info.append("Curl fallback returned empty or short payload")
            except Exception as e:
                debug_info.append(f"Curl subprocess fallback failed: {e}")

            return ""

        for attempt_idx, url in enumerate(urls_to_try):
            try:
                html = try_fetch_html(url)
                if not html:
                    debug_info.append(f"Skipping url {url} due to empty fetch body")
                    continue
                fetched_htmls.append(html)

                debug_info.append(f"Parsing body of size: {len(html)} characters")

                # Parse the initial data block dynamically with absolute resilience to spacing
                start_keyword = "ytInitialData"
                start_idx = html.find(start_keyword)
                debug_info.append(f"ytInitialData locate: {start_idx}")
                
                if start_idx != -1:
                    # Robust assignment symbol search and brace resolution
                    eq_idx = html.find("=", start_idx)
                    if eq_idx != -1:
                        json_start = html.find("{", eq_idx)
                        if json_start != -1:
                            try:
                                    decoder = json.JSONDecoder()
                                    data, end_pos = decoder.raw_decode(html[json_start:])
                                    debug_info.append(f"JSON raw_decode success (char count: {end_pos})")

                                # Comprehensive General Recursive Crawler
                                # Completely immune to list nesting depths or dynamic parent/child formats
                                    def crawl(obj):
                                        if not obj:
                                            return
                                        if isinstance(obj, list):
                                            for item in obj:
                                                crawl(item)
                                            return
                                        if isinstance(obj, dict):
                                            # Case A: playlistVideoRenderer
                                            if "playlistVideoRenderer" in obj:
                                                render = obj["playlistVideoRenderer"]
                                                v_id = render.get("videoId")
                                                if v_id and v_id not in seen_ids:
                                                    seen_ids.add(v_id)
                                                    title = "Unknown Title"
                                                    if "title" in render:
                                                        runs = render["title"].get("runs", [])
                                                        title = runs[0].get("text") if runs else render["title"].get("simpleText", "Unknown Title")
                                                    artist = "Unknown Artist"
                                                    if "shortBylineText" in render:
                                                        runs = render["shortBylineText"].get("runs", [])
                                                        artist = runs[0].get("text") if runs else "Unknown Artist"
                                                    
                                                    parsed_title, p_artist = self.clean_title(title)
                                                    if p_artist == "Unknown Artist":
                                                        p_artist = artist.replace(" - Topic", "")

                                                    tracks_data.append({
                                                        "title": parsed_title,
                                                        "artist": p_artist,
                                                        "url": f"https://music.youtube.com/watch?v={v_id}"
                                                    })

                                            # Case B: playlistItemRenderer
                                            if "playlistItemRenderer" in obj:
                                                render = obj["playlistItemRenderer"]
                                                v_id = render.get("videoId")
                                                if v_id and v_id not in seen_ids:
                                                    seen_ids.add(v_id)
                                                    title = "Unknown Title"
                                                    if "title" in render:
                                                        runs = render["title"].get("runs", [])
                                                        title = runs[0].get("text") if runs else render["title"].get("simpleText", "Unknown Title")
                                                    artist = "Unknown Artist"
                                                    if "shortBylineText" in render:
                                                        runs = render["shortBylineText"].get("runs", [])
                                                        artist = runs[0].get("text") if runs else "Unknown Artist"

                                                    parsed_title, p_artist = self.clean_title(title)
                                                    if p_artist == "Unknown Artist":
                                                        p_artist = artist.replace(" - Topic", "")

                                                    tracks_data.append({
                                                        "title": parsed_title,
                                                        "artist": p_artist,
                                                        "url": f"https://music.youtube.com/watch?v={v_id}"
                                                    })

                                            # Case C: musicResponsiveListItemRenderer (for YouTube Music Playlists/Albums)
                                            if "musicResponsiveListItemRenderer" in obj:
                                                render = obj["musicResponsiveListItemRenderer"]
                                                v_id = None
                                                if "playlistItemData" in render:
                                                    v_id = render["playlistItemData"].get("videoId")
                                                if not v_id and "playNavigationEndpoint" in render:
                                                    nav = render["playNavigationEndpoint"]
                                                    if "watchEndpoint" in nav:
                                                        v_id = nav["watchEndpoint"].get("videoId")
                                                if v_id and v_id not in seen_ids:
                                                    seen_ids.add(v_id)
                                                    title = "Unknown Title"
                                                    artist = "Unknown Artist"
                                                    flex_cols = render.get("flexColumns", [])
                                                    if len(flex_cols) > 0:
                                                        try:
                                                            col0 = flex_cols[0].get("musicResponsiveListItemFlexColumnRenderer", {})
                                                            runs = col0.get("text", {}).get("runs", [])
                                                            if runs:
                                                                title = runs[0].get("text", "Unknown Title")
                                                        except Exception:
                                                            pass
                                                    if len(flex_cols) > 1:
                                                        try:
                                                            col1 = flex_cols[1].get("musicResponsiveListItemFlexColumnRenderer", {})
                                                            runs = col1.get("text", {}).get("runs", [])
                                                            if runs:
                                                                artist = runs[0].get("text", "Unknown Artist")
                                                        except Exception:
                                                            pass
                                                    
                                                    parsed_title, p_artist = self.clean_title(title)
                                                    if p_artist == "Unknown Artist":
                                                        p_artist = artist.replace(" - Topic", "")

                                                    tracks_data.append({
                                                        "title": parsed_title,
                                                        "artist": p_artist,
                                                        "url": f"https://music.youtube.com/watch?v={v_id}"
                                                    })

                                            # Case D: playlistPanelVideoRenderer (for alternate list views)
                                            if "playlistPanelVideoRenderer" in obj:
                                                render = obj["playlistPanelVideoRenderer"]
                                                v_id = render.get("videoId")
                                                if v_id and v_id not in seen_ids:
                                                    seen_ids.add(v_id)
                                                    title = "Unknown Title"
                                                    if "title" in render:
                                                        runs = render["title"].get("runs", [])
                                                        title = runs[0].get("text") if runs else render["title"].get("simpleText", "Unknown Title")
                                                    artist = "Unknown Artist"
                                                    if "shortBylineText" in render:
                                                        runs = render["shortBylineText"].get("runs", [])
                                                        artist = runs[0].get("text") if runs else "Unknown Artist"
                                                    elif "longBylineText" in render:
                                                        runs = render["longBylineText"].get("runs", [])
                                                        artist = runs[0].get("text") if runs else "Unknown Artist"

                                                    parsed_title, p_artist = self.clean_title(title)
                                                    if p_artist == "Unknown Artist":
                                                        p_artist = artist.replace(" - Topic", "")

                                                    tracks_data.append({
                                                        "title": parsed_title,
                                                        "artist": p_artist,
                                                        "url": f"https://music.youtube.com/watch?v={v_id}"
                                                    })

                                            for val in obj.values():
                                                crawl(val)

                                    crawl(data)
                                    debug_info.append(f"tracks matched after deep crawl: {len(tracks_data)}")

                                    # Loose dictionary crawling fallback for non-standard system layouts
                                    if not tracks_data:
                                        def crawl_loose(obj):
                                            if not obj:
                                                return
                                            if isinstance(obj, list):
                                                for item in obj:
                                                    crawl_loose(item)
                                                return
                                            if isinstance(obj, dict):
                                                if "videoId" in obj and "title" in obj:
                                                    v_id = obj["videoId"]
                                                    if v_id and len(v_id) == 11 and v_id not in seen_ids:
                                                        seen_ids.add(v_id)
                                                        title = "Unknown Title"
                                                        t_node = obj["title"]
                                                        if isinstance(t_node, str):
                                                            title = t_node
                                                        elif isinstance(t_node, dict):
                                                            runs = t_node.get("runs", [])
                                                            title = runs[0].get("text") if runs else "Unknown Title"
                                                        
                                                        artist = "Unknown Artist"
                                                        if "shortBylineText" in obj and isinstance(obj["shortBylineText"], dict):
                                                            runs = obj["shortBylineText"].get("runs", [])
                                                            artist = runs[0].get("text") if runs else "Unknown Artist"
                                                        elif "author" in obj:
                                                            artist = obj["author"]

                                                        parsed_title, p_artist = self.clean_title(title)
                                                        if p_artist == "Unknown Artist":
                                                            p_artist = artist.replace(" - Topic", "")

                                                        tracks_data.append({
                                                            "title": parsed_title,
                                                            "artist": p_artist,
                                                            "url": f"https://music.youtube.com/watch?v={v_id}"
                                                        })
                                                for val in obj.values():
                                                    crawl_loose(val)

                                        crawl_loose(data)
                                        debug_info.append(f"tracks matched after loose crawl: {len(tracks_data)}")
                            except Exception as json_err:
                                debug_info.append(f"JSON indexing failed on attempt: {json_err}")

                # Fallback to direct RegEx capture on the general raw scrape markup if JSON is missing or incomplete
                if not tracks_data:
                    debug_info.append("Initiating Regex Crawler Fallback")
                    video_sections = re.findall(
                        r'\{"playlistVideoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"([^"]+)"\}\].*?"shortBylineText":\{"runs":\[\{"text":"([^"]+)"\}', 
                        html
                    )
                    debug_info.append(f"Direct RegEx captures: {len(video_sections)}")
                    for vid, raw_title, channel in video_sections:
                        if vid in seen_ids:
                            continue
                        seen_ids.add(vid)
                        parsed_title, artist = self.clean_title(raw_title)
                        if artist == "Unknown Artist":
                            artist = channel.replace(" - Topic", "")
                        tracks_data.append({
                            "title": parsed_title,
                            "artist": artist,
                            "url": f"https://music.youtube.com/watch?v={vid}"
                        })

                # If successful, abort loop early
                if tracks_data:
                    debug_info.append(f"Scraper successfully parsed {len(tracks_data)} results on this URL!")
                    break

            except Exception as item_err:
                debug_info.append(f"Failure on url {url}: {item_err}\n{traceback.format_exc()}")

        # Last resort fallback: fetch individual raw items using oEmbed and regex lists
        if not tracks_data:
            try:
                debug_info.append("Entering simple oEmbed lookup fallback chain")
                all_html = " ".join(fetched_htmls)
                simple_vids = re.findall(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', all_html)
                unique_vids = []
                for v in simple_vids:
                    if v not in seen_ids and len(unique_vids) < 30:
                        seen_ids.add(v)
                        unique_vids.append(v)
                debug_info.append(f"Unique vids extracted: {len(unique_vids)}")
                for vid in unique_vids:
                    try:
                        tr_details = self.public_get_track_details(vid)
                        tracks_data.append(tr_details)
                    except:
                        pass
                debug_info.append(f"tracks_data after oEmbed: {len(tracks_data)}")
            except Exception as fallback_err:
                debug_info.append(f"OEmbed extraction error: {fallback_err}")
                    
        # Safely dump execution analysis
        try:
            with open("debug_py.txt", "w") as df:
                df.write("\n".join(debug_info))
        except Exception as e:
            print(f"Error writing local debug_py.txt: {e}")
        try:
            with open("/debug_py.txt", "w") as df:
                df.write("\n".join(debug_info))
        except:
            pass

        if not tracks_data:
            raise Exception("Could not find any playlist track list via public scraping.")
            
        return tracks_data

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
