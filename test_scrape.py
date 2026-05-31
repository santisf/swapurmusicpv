import urllib.request
import xml.etree.ElementTree as ET

playlist_id = 'OLAK5uy_l3yCl4IOFKJ4vpj2jl6_gL3gZQOJPVP3w'
url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

try:
    req = urllib.request.Request(url, headers=headers)
    xml_data = urllib.request.urlopen(req, timeout=10).read()
    print('XML length:', len(xml_data))
    
    # Parse XML
    root = ET.fromstring(xml_data)
    
    # Namespaces
    ns = {
        'atom': 'http://www.w3.org/2005/Atom',
        'media': 'http://search.yahoo.com/mrss/',
        'yt': 'http://www.youtube.com/xml/schemas/2015'
    }
    
    tracks = []
    for entry in root.findall('atom:entry', ns):
        title_elem = entry.find('atom:title', ns)
        video_id_elem = entry.find('yt:videoId', ns)
        author_elem = entry.find('atom:author/atom:name', ns)
        
        title = title_elem.text if title_elem is not None else "Unknown"
        video_id = video_id_elem.text if video_id_elem is not None else ""
        author = author_elem.text if author_elem is not None else "Unknown"
        
        tracks.append({
            'title': title,
            'artist': author,
            'video_id': video_id
        })
        
    print('Parsed tracks from RSS:')
    for idx, t in enumerate(tracks):
        print(f"{idx+1}. {t['title']} - {t['artist']} (ID: {t['video_id']})")
        
except Exception as e:
    print('RSS failed:', e)
