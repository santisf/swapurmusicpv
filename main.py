import streamlit as st
import pandas as pd
import urllib.parse
import os
import json
import re
import requests
from dotenv import load_dotenv

# Import our custom services and matcher
from services.spotify_service import SpotifyService
from services.youtube_service import YouTubeService
from services.deezer_service import DeezerService
from utils.matcher import Matcher

# Load environment variables
load_dotenv()

def resolve_via_songlink(url):
    try:
        # Clean URL to maximize Songlink mapping accuracy
        clean_url = url
        if "youtu.be" in url:
            match = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", url)
            if match:
                video_id = match.group(1)
                clean_url = f"https://www.youtube.com/watch?v={video_id}"
        elif "youtube.com/watch" in url:
            parsed = urllib.parse.urlparse(url)
            q_params = urllib.parse.parse_qs(parsed.query)
            v_val = q_params.get("v")
            if v_val:
                clean_url = f"https://www.youtube.com/watch?v={v_val[0]}"
        elif "spotify.com" in url:
            parsed = urllib.parse.urlparse(url)
            track_match = re.search(r"/track/([a-zA-Z0-9]+)", parsed.path)
            if track_match:
                clean_url = f"https://open.spotify.com/track/{track_match.group(1)}"
            else:
                playlist_match = re.search(r"/playlist/([a-zA-Z0-9]+)", parsed.path)
                if playlist_match:
                    clean_url = f"https://open.spotify.com/playlist/{playlist_match.group(1)}"

        encoded_url = urllib.parse.quote(clean_url)
        songlink_api = f"https://api.song.link/v1-alpha.1/links?url={encoded_url}"
        res = requests.get(songlink_api, timeout=10)
        if res.ok:
            data = res.json()
            links = data.get("linksByPlatform", {})
            
            sp_url = links.get("spotify", {}).get("url")
            yt_url = links.get("youtubeMusic", {}).get("url") or links.get("youtube", {}).get("url")
            dz_url = links.get("deezer", {}).get("url")
            
            return {
                "spotify": sp_url,
                "youtube": yt_url,
                "deezer": dz_url
            }
    except Exception as e:
        print(f"Songlink resolution error: {e}")
    return {}

def search_via_gemini_grounding(title, artist, platform):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "MY_GEMINI_API_KEY":
        try:
            if "GEMINI_API_KEY" in st.secrets:
                api_key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass
    if not api_key or api_key == "MY_GEMINI_API_KEY" or not HAS_GENAI_LIB:
        return None
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"Busca en Google y encuentra el enlace oficial de {platform} para la canción '{title}' de '{artist}'."
        system_inst = f"Eres un asistente de búsqueda musical de SwapUrMusic. Tu único objetivo es encontrar el enlace correspondiente a {platform} para la canción especificada de este artista. Utiliza la herramienta de búsqueda de Google. Responde ÚNICAMENTE con la URL directa encontrada. No incluyas explicaciones, ni introducciones, ni bloques de código, solo la URL."
        
        response = client.models.generateContent(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"googleSearch": {}}],
                temperature=0.1,
                systemInstruction=system_inst
            )
        )
        
        text = response.text.strip() if response.text else ""
        if platform == "Spotify":
            match = re.search(r"https://open\.spotify\.com/(?:[a-zA-Z0-9_-]+/)?track/([a-zA-Z0-9]+)", text)
            if match:
                return f"https://open.spotify.com/track/{match.group(1)}"
        elif platform == "YouTube Music":
            match = re.search(r"https://(?:music\.|www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})", text) or re.search(r"https://youtu\.be/([a-zA-Z0-9_-]{11})", text)
            if match:
                return f"https://music.youtube.com/watch?v={match.group(1)}"
        elif platform == "Deezer":
            match = re.search(r"https://(?:www\.)?deezer\.com/(?:[a-zA-Z0-9_-]+/)?track/([0-9]+)", text)
            if match:
                return f"https://www.deezer.com/track/{match.group(1)}"
    except Exception as e:
        print(f"Gemini grounding search for {platform} failed: {e}")
    return None


# Import Gemini if available
try:
    from google import genai
    from google.genai import types
    HAS_GENAI_LIB = True
except ImportError:
    HAS_GENAI_LIB = False

@st.cache_resource
def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "MY_GEMINI_API_KEY":
        try:
            if "GEMINI_API_KEY" in st.secrets:
                api_key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass
    if api_key and api_key != "MY_GEMINI_API_KEY" and HAS_GENAI_LIB:
        try:
            return genai.Client(api_key=api_key)
        except Exception as e:
            print(f"Error initializing Gemini Client in main.py: {e}")
    return None

def parse_song_with_gemini(user_message, client):
    if not client or not HAS_GENAI_LIB:
        # Simplistic offline parsing fallback if Gemini key is missing or error
        match = re.search(r'(?:buscar|busca|búscame|escuchar|escucha)\s+(.+?)(?:\s+(?:de|by)\s+(.+))?$', user_message, re.IGNORECASE)
        if match:
            return {"song_found": True, "title": match.group(1).strip(), "artist": match.group(2).strip() if match.group(2) else ""}
        return {"song_found": True, "title": user_message.strip(), "artist": ""}
        
    syst_instruct = """
    Eres el clasificador de texto de SwapUrMusic. Tu única misión es extraer el NOMBRE DE LA CANCIÓN y el ARTISTA de la petición del usuario.
    Responde estrictamente en formato JSON con la siguiente estructura, sin bloques de código, sin markdown, sin texto adicional:
    {
      "song_found": true/false (si el mensaje del usuario expresa clara intención de buscar una canción o pista específica),
      "title": "nombre de la pista encontrada" (o vacío si no se encuentra),
      "artist": "nombre del músico, grupo o artista" (o de Topic, o vacío si no se encuentra)
    }
    Ejemplos:
    - User: "búscame Creo de Callejeros" -> {"song_found": true, "title": "Creo", "artist": "Callejeros"}
    - User: "quiero escuchar dios es un stalker de rosalia" -> {"song_found": true, "title": "Dios Es Un Stalker", "artist": "ROSALÍA"}
    - User: "pon la cancion de callejeros creo" -> {"song_found": true, "title": "Creo", "artist": "Callejeros"}
    - User: "hola, qué tal estás?" -> {"song_found": false, "title": "", "artist": ""}
    """
    try:
        response = client.models.generateContent(
            model="gemini-3.5-flash",
            contents=user_message,
            config=types.GenerateContentConfig(
                systemInstruction=syst_instruct,
                responseMimeType="application/json",
                temperature=0.1
            )
        )
        return json.loads(response.text.strip())
    except Exception as e:
        print(f"Gemini parse exception: {e}")
        return {"song_found": True, "title": user_message.strip(), "artist": ""}

# Set page config
st.set_page_config(
    page_title="SwapUrMusic - Convertidor de Enlaces de Música",
    page_icon="🎵",
    layout="centered"  # Centered layout looks much cleaner and premium than wide
)

# Custom Premium Styling
st.markdown("""
<style>
    /* Main container and title alignment */
    .stApp {
        background-color: #0f111a;
        color: #f1f3f9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    /* Logo hover animation */
    .logo-svg {
        transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), filter 0.4s ease;
        transform-origin: center;
        display: block;
        margin: 0 auto;
    }
    .logo-svg:hover {
        transform: scale(1.08) rotate(3deg);
        filter: drop-shadow(0 0 35px rgba(168, 85, 247, 0.85)) brightness(1.15) !important;
    }

    @keyframes shine-sweep {
        0% {
            background-position: -200% center;
        }
        100% {
            background-position: 200% center;
        }
    }

    /* Elegant Title and Header styling */
    .main-title {
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(120deg, #a855f7 0%, #3b82f6 30%, #ffffff 50%, #3b82f6 70%, #a855f7 100%);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.5rem;
        transition: filter 0.4s ease, transform 0.3s ease;
        cursor: default;
    }
    .main-title:hover {
        animation: shine-sweep 1.8s infinite linear;
        filter: drop-shadow(0 0 18px rgba(168, 85, 247, 0.75)) brightness(1.3);
        transform: translateY(-1px) scale(1.03);
    }
    .main-subtitle {
        font-size: 1.15rem;
        color: #94a3b8;
        text-align: center;
        margin-bottom: 2.5rem;
    }
    
    /* Premium style wrapper for Streamlit's native container with border=True */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #1a1c2d !important;
        border-radius: 16px !important;
        padding: 2rem !important;
        border: 1px solid #334155 !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45) !important;
        margin-bottom: 2.5rem !important;
    }
    
    /* Container/Card styling for input elements */
    .input-card {
        background-color: #1e2235;
        border-radius: 16px;
        padding: 2rem;
        border: 1px solid #334155;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        margin-bottom: 2rem;
    }
    
    /* Beautiful single track visualizer card */
    .track-result-card {
        background: linear-gradient(145deg, #1e1b4b 0%, #0f172a 100%);
        border-radius: 20px;
        padding: 2.5rem;
        border: 1px solid #4338ca;
        box-shadow: 0 15px 35px rgba(0, 0, 0, 0.5);
        margin-top: 2rem;
        text-align: center;
    }
    .track-title {
        font-size: 2rem;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 0.25rem;
        letter-spacing: -0.025em;
    }
    .track-artist {
        font-size: 1.25rem;
        font-weight: 500;
        color: #a5b4fc;
        margin-bottom: 1.5rem;
    }
    
    /* Clickable Platform Action Buttons */
    .platform-link-container {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        max-width: 450px;
        margin: 2rem auto 0 auto;
    }
    
    .platform-btn {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 24px;
        border-radius: 12px;
        font-size: 1rem;
        font-weight: 700;
        text-decoration: none !important;
        color: #ffffff !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    }
    .platform-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(0,0,0,0.4);
        filter: brightness(1.1);
    }
    
    .btn-spotify {
        background: linear-gradient(135deg, #1DB954 0%, #179c46 100%);
    }
    .btn-youtube {
        background: linear-gradient(135deg, #FF0000 0%, #cc0000 100%);
    }
    .btn-deezer {
        background: linear-gradient(135deg, #ff007f 0%, #9bc225 100%);
        background-color: #121216; /* Fallback */
    }
    .btn-deezer-actual {
        background: linear-gradient(135deg, #121216 0%, #2a2a35 100%);
        border: 1px solid #ff007f;
    }
    
    .btn-disabled {
        background: #1e293b !important;
        background-color: #1e293b !important;
        color: #64748b !important;
        border: 1px solid #334155 !important;
        cursor: not-allowed !important;
        box-shadow: none !important;
        pointer-events: none !important;
        opacity: 0.65;
    }
    
    .btn-text {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .badge-platforms {
        background-color: rgba(255, 255, 255, 0.15);
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.05em;
    }
    
    /* Custom footer */
    .custom-footer {
        text-align: center;
        margin-top: 4rem;
        padding-top: 1.5rem;
        border-top: 1px solid #1e293b;
        color: #64748b;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# Instantiate background services
spotify_service = SpotifyService()
youtube_service = YouTubeService()
deezer_service = DeezerService()
matcher = Matcher()

# Header Section
st.markdown(
    """<div style="text-align: center; margin-bottom: 1.5rem; margin-top: 1.5rem;">
<svg class="logo-svg" viewBox="0 0 500 500" width="180" height="180" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 0 25px rgba(168, 85, 247, 0.45));">
<defs>
<linearGradient id="purpleBlueGrad" x1="0%" y1="0%" x2="100%" y2="100%">
<stop offset="0%" stop-color="#bf5af2" />
<stop offset="100%" stop-color="#0a84ff" />
</linearGradient>
<radialGradient id="ringGlow" cx="50%" cy="50%" r="50%">
<stop offset="70%" stop-color="#18113c" stop-opacity="0.8" />
<stop offset="100%" stop-color="#090d16" stop-opacity="1" />
</radialGradient>
</defs>
<circle cx="250" cy="250" r="210" fill="url(#ringGlow)" stroke="url(#purpleBlueGrad)" stroke-width="4" />
<circle cx="250" cy="250" r="195" stroke="#bf5af2" stroke-width="1.5" stroke-dasharray="25 15 5 15" stroke-opacity="0.6" fill="none" />
<circle cx="250" cy="250" r="185" stroke="#0a84ff" stroke-width="1" stroke-dasharray="5 10 30 10" stroke-opacity="0.4" fill="none" />
<path d="M 250 250 C 210 170, 130 170, 130 250 C 130 330, 210 330, 250 250 C 290 170, 370 170, 370 250 C 370 330, 290 330, 250 250 Z" fill="none" stroke="url(#purpleBlueGrad)" stroke-width="20" stroke-linecap="round" />
<path d="M 250 250 C 210 180, 140 180, 140 250 C 140 320, 210 320, 250 250 C 290 180, 360 180, 360 250 C 360 320, 290 320, 250 250 Z" fill="none" stroke="#2a1b5c" stroke-width="8" stroke-linecap="round" />
<path d="M 250 250 C 210 190, 150 190, 150 250 C 150 310, 210 310, 250 250 C 290 190, 350 190, 350 250 C 350 310, 290 310, 250 250 Z" fill="none" stroke="url(#purpleBlueGrad)" stroke-width="3" stroke-linecap="round" />
<path d="M 175 198 L 190 205 L 175 215" fill="none" stroke="#0a84ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
<path d="M 325 302 L 310 295 L 325 285" fill="none" stroke="#bf5af2" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
<path d="M 230 100 A 30 30 0 0 1 270 100 L 270 115 L 260 115 L 250 130 L 240 115 L 230 115 Z" fill="#bf5af2" opacity="0.9" />
<path d="M 242 105 L 252 105 L 252 113 M 244 110 L 258 110" stroke="#090d16" stroke-width="2.5" stroke-linecap="round" fill="none" />
<g transform="translate(210, 355)" fill="#0a84ff" opacity="0.95">
<rect x="0" y="20" width="8" height="20" rx="4" />
<rect x="15" y="5" width="8" height="35" rx="4" fill="url(#purpleBlueGrad)" />
<rect x="30" y="12" width="8" height="28" rx="4" fill="url(#purpleBlueGrad)" />
<rect x="45" y="2" width="8" height="38" rx="4" fill="url(#purpleBlueGrad)" />
<rect x="60" y="15" width="8" height="25" rx="4" />
<rect x="75" y="22" width="8" height="18" rx="4" />
</g>
<g transform="translate(160, 235)">
<circle cx="10" cy="22" r="6" fill="#0a84ff" />
<path d="M 16 22 L 16 5 L 28 8 L 28 15 L 16 12" fill="none" stroke="#0a84ff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
</g>
<polygon points="310,235 310,265 335,250" fill="#bf5af2" />
</svg>
</div>""",
    unsafe_allow_html=True
)

if True:
    st.markdown("<h1 class='main-title'>SwapUrMusic</h1>", unsafe_allow_html=True)
    st.markdown("<p class='main-subtitle'>Convierte y comparte tus canciones y listas de reproducción al instante / Match and swap your music links</p>", unsafe_allow_html=True)

    # Main Form Container (Native container with custom styling overrides)
    with st.container(border=True):
        input_url = st.text_input(
            "💡 Enlace de canción o Playlist / Song or Playlist Link:", 
            placeholder="Pega un enlace de Spotify, YouTube o Deezer...",
            key="converter_input_url"
        )

        source_platform = st.selectbox(
            "Plataforma de Origen / Source Platform:",
            ["Detectar Automáticamente (Recomendado)", "Spotify", "YouTube Music", "Deezer"],
            key="converter_source_platform"
        )

        st.markdown("<div style='margin-top: 1.5rem;'>", unsafe_allow_html=True)
        convert_btn = st.button("🚀 Convertir Enlace / Convert Link", use_container_width=True, key="converter_btn")
        st.markdown("</div>", unsafe_allow_html=True)

    # Main logic loop
    if convert_btn:
        if not input_url:
            st.error("Por favor ingresa un enlace válido antes de continuar.")
        else:
            detected_platform = None
            source_id = None
            media_type = None  # "track" or "playlist"
            
            # Determine source platform logic
            if "Detectar Automáticamente" in source_platform:
                if "spotify.com" in input_url:
                    detected_platform = "Spotify"
                    media_type, source_id = spotify_service.extract_id(input_url)
                elif "youtube.com" in input_url or "youtu.be" in input_url or "music.youtube.com" in input_url:
                    detected_platform = "YouTube Music"
                    media_type, source_id = youtube_service.extract_id(input_url)
                elif "deezer.com" in input_url or "deezer.page.link" in input_url or "link.deezer.com" in input_url:
                    detected_platform = "Deezer"
                    media_type, source_id = deezer_service.extract_id(input_url)
                else:
                    st.error("No se pudo detectar la plataforma de origen automáticamente. Por favor selecciónala de forma manual.")
            else:
                detected_platform = source_platform
                if detected_platform == "Spotify":
                    media_type, source_id = spotify_service.extract_id(input_url)
                elif detected_platform == "YouTube Music":
                    media_type, source_id = youtube_service.extract_id(input_url)
                elif detected_platform == "Deezer":
                    media_type, source_id = deezer_service.extract_id(input_url)

            if not source_id or not media_type:
                st.error("Formato de URL no reconocido. Asegúrate de copiar un enlace de canción (track) o lista de reproducción (playlist) válido.")
            else:
                tracks_to_match = []
                with st.spinner("Buscando metadatos originales..."):
                    try:
                        if media_type == "track":
                            if detected_platform == "Spotify":
                                tracks_to_match.append(spotify_service.get_track_details(source_id))
                            elif detected_platform == "YouTube Music":
                                tracks_to_match.append(youtube_service.get_track_details(source_id))
                            elif detected_platform == "Deezer":
                                tracks_to_match.append(deezer_service.get_track_details(source_id))
                        else:  # Playlist
                            if detected_platform == "Spotify":
                                tracks_to_match = spotify_service.get_playlist_tracks(source_id)
                            elif detected_platform == "YouTube Music":
                                tracks_to_match = youtube_service.get_playlist_tracks(source_id)
                            elif detected_platform == "Deezer":
                                tracks_to_match = deezer_service.get_playlist_tracks(source_id)
                    except Exception as ex:
                        import traceback
                        st.error(f"Error cargando metadatos originales: {ex}")
                        st.text(traceback.format_exc())
                        if os.path.exists("/debug_py.txt"):
                            st.subheader("Depuración interna / Diagnostic Log:")
                            with open("/debug_py.txt") as df:
                                st.code(df.read())
                        elif os.path.exists("./debug_py.txt"):
                            st.subheader("Depuración interna / Diagnostic Log:")
                            with open("./debug_py.txt") as df:
                                st.code(df.read())
                        tracks_to_match = []

                if tracks_to_match:
                    # ====== RENDER TRACK CARD (SINGLE TRACK CONVERSION) ======
                    if media_type == "track":
                        orig_track = tracks_to_match[0]
                        title = orig_track.get("title", "")
                        artist = orig_track.get("artist", "")
                        
                        st.toast("🎉 ¡Canción encontrada con éxito!", icon="🎵")
                        
                        # Search destination links
                        sp_link, yt_link, dz_link = "N/A", "N/A", "N/A"
                        matched_scores = []
                        
                        # Store original link
                        if detected_platform == "Spotify":
                            sp_link = orig_track.get("url", "N/A")
                        elif detected_platform == "YouTube Music":
                            yt_link = orig_track.get("url", "N/A")
                        elif detected_platform == "Deezer":
                            dz_link = orig_track.get("url", "N/A")
                            
                        with st.spinner("Buscando coincidencias de precisión en otras plataformas..."):
                            # Try Songlink first as a high-precision helper!
                            sl_res = resolve_via_songlink(input_url)
                            
                            # Get Spotify target
                            if detected_platform != "Spotify":
                                sp_link = sl_res.get("spotify") or "N/A"
                                if sp_link == "N/A" or not sp_link:
                                    candidates = spotify_service.search_track(title, artist)
                                    best_cand, score, _ = matcher.find_best_match(title, artist, candidates)
                                    if best_cand:
                                        sp_link = best_cand["url"]
                                        matched_scores.append(score)
                                    else:
                                        gem_link = search_via_gemini_grounding(title, artist, "Spotify")
                                        if gem_link:
                                            sp_link = gem_link
                                            matched_scores.append(0.95)
                                        else:
                                            matched_scores.append(0.0)
                                else:
                                    matched_scores.append(1.0)
                                    
                            # Get YouTube Music target
                            if detected_platform != "YouTube Music":
                                yt_link = sl_res.get("youtube") or "N/A"
                                if yt_link == "N/A" or not yt_link:
                                    candidates = youtube_service.search_track(title, artist)
                                    best_cand, score, _ = matcher.find_best_match(title, artist, candidates)
                                    if best_cand:
                                        yt_link = best_cand["url"]
                                        matched_scores.append(score)
                                    else:
                                        gem_link = search_via_gemini_grounding(title, artist, "YouTube Music")
                                        if gem_link:
                                            yt_link = gem_link
                                            matched_scores.append(0.95)
                                        else:
                                            matched_scores.append(0.0)
                                else:
                                    matched_scores.append(1.0)
                                    
                            # Get Deezer target
                            if detected_platform != "Deezer":
                                dz_link = sl_res.get("deezer") or "N/A"
                                if dz_link == "N/A" or not dz_link:
                                    candidates = deezer_service.search_track(title, artist)
                                    best_cand, score, _ = matcher.find_best_match(title, artist, candidates)
                                    if best_cand:
                                        dz_link = best_cand["url"]
                                        matched_scores.append(score)
                                    else:
                                        gem_link = search_via_gemini_grounding(title, artist, "Deezer")
                                        if gem_link:
                                            dz_link = gem_link
                                            matched_scores.append(0.95)
                                        else:
                                            matched_scores.append(0.0)
                                else:
                                    matched_scores.append(1.0)

                        # Compute matching quality
                        avg_score = sum(matched_scores) / len(matched_scores) if matched_scores else 0.0
                        if avg_score >= 0.85:
                            qual_col = "🟢 Coincidencia Exacta / High Accuracy"
                        elif avg_score >= 0.60:
                            qual_col = "🟡 Coincidencia Cercana / Check Match"
                        else:
                            qual_col = "🔵 Búsqueda Directa Fallback / Search Query Link"

                        # Generate HTML buttons dynamically based on whether link was matched
                        if sp_link != "N/A" and sp_link:
                            sp_btn = f"""<a href='{sp_link}' target='_blank' class='platform-btn btn-spotify'>
                                <span class='btn-text'>🟢 Escuchar en Spotify</span>
                                <span class='badge-platforms'>ABRIR / OPEN</span>
                            </a>"""
                        else:
                            sp_btn = """<div class='platform-btn btn-disabled'>
                                <span class='btn-text'>🟢 No disponible en Spotify</span>
                                <span class='badge-platforms'>N/A</span>
                            </div>"""

                        if yt_link != "N/A" and yt_link:
                            yt_btn = f"""<a href='{yt_link}' target='_blank' class='platform-btn btn-youtube'>
                                <span class='btn-text'>🔴 Escuchar en YouTube Music</span>
                                <span class='badge-platforms'>ABRIR / OPEN</span>
                            </a>"""
                        else:
                            yt_btn = """<div class='platform-btn btn-disabled'>
                                <span class='btn-text'>🔴 No disponible en YouTube Music</span>
                                <span class='badge-platforms'>N/A</span>
                            </div>"""

                        if dz_link != "N/A" and dz_link:
                            dz_btn = f"""<a href='{dz_link}' target='_blank' class='platform-btn btn-deezer btn-deezer-actual'>
                                <span class='btn-text'>🎵 Escuchar en Deezer</span>
                                <span class='badge-platforms'>ABRIR / OPEN</span>
                            </a>"""
                        else:
                            dz_btn = """<div class='platform-btn btn-disabled'>
                                <span class='btn-text'>🎵 No disponible en Deezer</span>
                                <span class='badge-platforms'>N/A</span>
                            </div>"""

                        # Beautiful single card display
                        st.markdown(f"""<div class='track-result-card'>
    <div style='font-size: 3rem; margin-bottom: 0.5rem;'>🎵</div>
    <div class='track-title'>{title}</div>
    <div class='track-artist'>{artist}</div>
    <div style='margin-bottom: 2rem;'>
        <span class='badge-platforms'>{qual_col} (Confianza: {int(avg_score * 100)}%)</span>
    </div>
    <div class='platform-link-container'>
        {sp_btn}
        {yt_btn}
        {dz_btn}
    </div>
    </div>""", unsafe_allow_html=True)
                        
                        if avg_score < 0.60:
                            st.warning("⚠️ **Aviso de coincidencia:** No pudimos confirmar coincidencias exactas para este enlace en todas las plataformas. Esto suele ocurrir si la URL ingresada no es una pista musical (por ejemplo, un videotutorial o tutorial técnico) o si no está disponible comercialmente en estos catálogos.")
                        
                    # ====== RENDER PLAYLIST VISUALIZER ======
                    else: 
                        st.toast(f"🎉 Se importó un playlist con {len(tracks_to_match)} canciones.", icon="📋")
                        results = []
                        progress_bar = st.progress(0)
                        
                        for i, track in enumerate(tracks_to_match):
                            p_title = track.get("title", "")
                            p_artist = track.get("artist", "")
                            
                            row = {
                                "Canción / Song": p_title,
                                "Artista / Artist": p_artist,
                                "Spotify Link": None,
                                "YouTube Link": None,
                                "Deezer Link": None,
                                "Resultado / Status": "Exact Match",
                                "Confianza / Match Score": 1.0
                            }
                            
                            p_sp_link, p_yt_link, p_dz_link = None, None, None
                            scores = []
                            
                            if detected_platform == "Spotify":
                                p_sp_link = track.get("url", None)
                            elif detected_platform == "YouTube Music":
                                p_yt_link = track.get("url", None)
                            elif detected_platform == "Deezer":
                                p_dz_link = track.get("url", None)
                                
                            # Search Spotify
                            if detected_platform != "Spotify":
                                candidates = spotify_service.search_track(p_title, p_artist)
                                best_cand, score, _ = matcher.find_best_match(p_title, p_artist, candidates)
                                if best_cand:
                                    p_sp_link = best_cand["url"]
                                scores.append(score)
                                    
                            # Search YouTube Music
                            if detected_platform != "YouTube Music":
                                candidates = youtube_service.search_track(p_title, p_artist)
                                best_cand, score, _ = matcher.find_best_match(p_title, p_artist, candidates)
                                if best_cand:
                                    p_yt_link = best_cand["url"]
                                scores.append(score)
                                    
                            # Search Deezer
                            if detected_platform != "Deezer":
                                candidates = deezer_service.search_track(p_title, p_artist)
                                best_cand, score, _ = matcher.find_best_match(p_title, p_artist, candidates)
                                if best_cand:
                                    p_dz_link = best_cand["url"]
                                scores.append(score)

                            row["Spotify Link"] = p_sp_link
                            row["YouTube Link"] = p_yt_link
                            row["Deezer Link"] = p_dz_link
                            
                            mean_score = sum(scores) / len(scores) if scores else 0.0
                            row["Confianza / Match Score"] = round(mean_score, 2)
                            
                            if mean_score >= 0.85:
                                row["Resultado / Status"] = "🟩 Alta Precisión / Exact Match"
                            elif mean_score >= 0.60:
                                row["Resultado / Status"] = "🟨 Intermedio / Fuzzy Match"
                            else:
                                row["Resultado / Status"] = "🟦 No Encontrado"
                                
                            results.append(row)
                            progress_bar.progress((i + 1) / len(tracks_to_match))
                            
                        st.success(f"🎉 Conversión finalizada con éxito.")
                        
                        df = pd.DataFrame(results)
                        
                        st.subheader("🎉 Canciones Convertidas / Converted Playlists")
                        st.dataframe(
                            df,
                            column_config={
                                "Spotify Link": st.column_config.LinkColumn("Enlace Spotify", max_chars=100),
                                "YouTube Link": st.column_config.LinkColumn("YouTube Music", max_chars=100),
                                "Deezer Link": st.column_config.LinkColumn("Deezer Link", max_chars=100),
                            },
                            use_container_width=True,
                            hide_index=True
                        )
                        
                        # Metrics and Action
                        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
                        col1, col2 = st.columns(2)
                        
                        total = len(results)
                        exact = sum(1 for r in results if "Alta Precisión" in r["Resultado / Status"])
                        
                        col1.metric("Total Canciones", total)
                        col2.metric("Coincidencias Exactas", f"{exact} / {total} ({int(exact/total*100)}%)" if total else "0/0")
                        
                        # CSV Export
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Descargar Playlist Convertida (CSV) / Export Playlist CSV",
                            data=csv,
                            file_name="swap_ur_music_playlist.csv",
                            mime="text/csv",
                            use_container_width=True,
                            key="download_csv_btn"
                        )

# Elegant Footer
st.markdown("""
<div class='custom-footer'>
    <p>✨ <b>SwapUrMusic App</b> • Conversor Offline Inteligente. Desarrollado con 💖 utilizando Python & Streamlit.</p>
</div>
""", unsafe_allow_html=True)
