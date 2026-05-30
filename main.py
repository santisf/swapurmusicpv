import streamlit as st
import pandas as pd
import urllib.parse
import os
from dotenv import load_dotenv

# Import our custom services and matcher
from services.spotify_service import SpotifyService
from services.youtube_service import YouTubeService
from services.deezer_service import DeezerService
from utils.matcher import Matcher

# Load environment variables
load_dotenv()

# Set page config
st.set_page_config(
    page_title="SwapUrMusic - Convertidor de Enlaces de Música",
    page_icon="🎵",
    layout="wide"
)

# Sidebar and Configuration Status
st.sidebar.title("🛠️ Estado de Configuración / Setup Status")

spotify_service = SpotifyService()
youtube_service = YouTubeService()
deezer_service = DeezerService()
matcher = Matcher()

if spotify_service.is_configured():
    st.sidebar.success("✅ Spotify API: Configurada con Credenciales")
else:
    st.sidebar.info("🌐 Spotify API: Modo Scraping Público Activo (Sin credenciales)")

if youtube_service.yt is not None:
    st.sidebar.success("✅ YouTube API: Configurada con Llave")
else:
    st.sidebar.success("🌐 YouTube Music: Modo Scraping Público Activo (Sin llave)")

st.sidebar.success("✅ Deezer API: Activa (Pública y Gratuita)")

# About Matcher
import os
if os.getenv("GEMINI_API_KEY"):
    st.sidebar.info("🤖 AI-Matching: Activado con Gemini (Modelo en la Nube)")
elif matcher.model:
    st.sidebar.info("🧠 AI-Matching: Activado con SentenceTransformers (Local)")
else:
    st.sidebar.warning("⚡ Matching: Activado con Algoritmo de Distancia de Levenshtein (Rápido y Local)")

# Title and App Header
st.title("🎵 SwapUrMusic - Streamlit Edition")
st.markdown("""
### ¡Convierte tus enlaces de música de forma rápida y gratuita! / Convert your music links easily!
Convierte canciones o listas de reproducción (Playlists) entre **Spotify**, **YouTube Music**, y **Deezer** sin perder la pista.
""")

# Input section
st.subheader("1. Ingresa tu enlace de música / Enter your music link")
input_url = st.text_input("Enlace de canción o Playlist:", placeholder="Ej: https://open.spotify.com/track/1TqHcm3i8yDL9XPHXe1oQg?si=7220777af7c84734")

# Source selector
source_platform = st.selectbox(
    "Detectar Plataforma de Origen / Source Platform:",
    ["Detectar Automáticamente (Recomendado)", "Spotify", "YouTube Music", "Deezer"]
)

convert_btn = st.button("🚀 Convertir Enlace / Convert Link", use_container_width=True)

# Main logic loop
if convert_btn:
    if not input_url:
        st.error("Por favor ingresa un enlace válido antes de continuar.")
    else:
        # Detect source and parse
        detected_platform = None
        source_id = None
        media_type = None # "track" or "playlist"
        
        # Determine service platform
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
                st.error("No se pudo detectar la plataforma automáticamente. Por favor selecciónala de forma manual.")
        else:
            detected_platform = source_platform
            if detected_platform == "Spotify":
                media_type, source_id = spotify_service.extract_id(input_url)
            elif detected_platform == "YouTube Music":
                media_type, source_id = youtube_service.extract_id(input_url)
            elif detected_platform == "Deezer":
                media_type, source_id = deezer_service.extract_id(input_url)

        if not source_id or not media_type:
            st.error("Formato de URL no reconocido. Asegúrate de copiar un enlace válido de canción o lista de reproducción.")
        else:
            st.info(f"🔍 Identificado: **{detected_platform}** - Tipo: **{media_type.capitalize()}** (ID: `{source_id}`). Buscando coincidencias...")
            
            # Retrieve source tracks
            tracks_to_match = []
            try:
                with st.spinner("Descargando metadatos originales de la canción / playlist..."):
                    if media_type == "track":
                        if detected_platform == "Spotify":
                            tracks_to_match.append(spotify_service.get_track_details(source_id))
                        elif detected_platform == "YouTube Music":
                            tracks_to_match.append(youtube_service.get_track_details(source_id))
                        elif detected_platform == "Deezer":
                            tracks_to_match.append(deezer_service.get_track_details(source_id))
                    else: # Playlist
                        if detected_platform == "Spotify":
                            tracks_to_match = spotify_service.get_playlist_tracks(source_id)
                        elif detected_platform == "YouTube Music":
                            tracks_to_match = youtube_service.get_playlist_tracks(source_id)
                        elif detected_platform == "Deezer":
                            tracks_to_match = deezer_service.get_playlist_tracks(source_id)
            except Exception as ex:
                st.error(f"Error cargando metadatos iniciales: {ex}")
                tracks_to_match = []
                
            if tracks_to_match:
                st.success(f"🎵 ¡Se encontró {len(tracks_to_match)} canción(es)! Buscando en el resto de las plataformas con algoritmos de precisión...")
                
                results = []
                progress_bar = st.progress(0)
                
                # Iterate and match
                for i, track in enumerate(tracks_to_match):
                    title = track.get("title", "")
                    artist = track.get("artist", "")
                    
                    row = {
                        "Canción / Song": title,
                        "Artista / Artist": artist,
                        "Spotify Link": "N/A",
                        "YouTube Link": "N/A",
                        "Deezer Link": "N/A",
                        "Resultado / Status": "🟩 Coincidencia Exacta",
                        "Confianza / Confidence": 1.0
                    }
                    
                    # Store known link for the source and search for the target platforms
                    sp_link, yt_link, dz_link = "N/A", "N/A", "N/A"
                    scores = []
                    
                    if detected_platform == "Spotify":
                        sp_link = track.get("url", "N/A")
                    elif detected_platform == "YouTube Music":
                        yt_link = track.get("url", "N/A")
                    elif detected_platform == "Deezer":
                        dz_link = track.get("url", "N/A")
                        
                    # 1. Search Spotify if target
                    if detected_platform != "Spotify":
                        if spotify_service.is_configured():
                            candidates = spotify_service.search_track(title, artist)
                            best_cand, score, status = matcher.find_best_match(title, artist, candidates)
                            if best_cand:
                                sp_link = best_cand["url"]
                                scores.append(score)
                        else:
                            # Search query fallback
                            pass
                            
                    # 2. Search YouTube if target
                    if detected_platform != "YouTube Music":
                        if youtube_service.is_configured():
                            candidates = youtube_service.search_track(title, artist)
                            best_cand, score, status = matcher.find_best_match(title, artist, candidates)
                            if best_cand:
                                yt_link = best_cand["url"]
                                scores.append(score)
                        else:
                            # Search query fallback
                            pass
                            
                    # 3. Search Deezer if target
                    if detected_platform != "Deezer":
                        candidates = deezer_service.search_track(title, artist)
                        best_cand, score, status = matcher.find_best_match(title, artist, candidates)
                        if best_cand:
                            dz_link = best_cand["url"]
                            scores.append(score)

                    # --- Strict guards: if link is still N/A, provide a clean search query link ---
                    encoded_query = urllib.parse.quote(f"{artist} {title}")
                    if sp_link == "N/A":
                        sp_link = f"https://open.spotify.com/search/{encoded_query}"
                    if yt_link == "N/A":
                        yt_link = f"https://music.youtube.com/search?q={encoded_query}"
                    if dz_link == "N/A":
                        dz_link = f"https://www.deezer.com/search/{encoded_query}"

                    # Update columns
                    row["Spotify Link"] = sp_link
                    row["YouTube Link"] = yt_link
                    row["Deezer Link"] = dz_link
                    
                    mean_score = sum(scores) / len(scores) if scores else 1.0
                    status_str, status_label = matcher.classify_match(mean_score)
                    
                    # Style labels for UI
                    if mean_score >= 0.85:
                        row["Resultado / Status"] = "🟩 Coincidencia Exacta / Match"
                    elif mean_score >= 0.60:
                        row["Resultado / Status"] = "🟨 Coincidencias Similares"
                    else:
                        row["Resultado / Status"] = "🟥 Búsqueda Directa Fallback"
                        
                    row["Confianza / Confidence"] = round(mean_score, 2)
                    
                    results.append(row)
                    progress_bar.progress((i + 1) / len(tracks_to_match))
                
                # Show results in Streamlit Dataframe
                st.subheader("🎉 Enlaces Encontrados / Conversion Results")
                df = pd.DataFrame(results)
                
                # Style links dynamically as real clickable anchors in Streamlit
                st.dataframe(
                    df,
                    column_config={
                        "Spotify Link": st.column_config.LinkColumn("Enlace Spotify", max_chars=100),
                        "YouTube Link": st.column_config.LinkColumn("Enlace YouTube Music", max_chars=100),
                        "Deezer Link": st.column_config.LinkColumn("Enlace Deezer", max_chars=100),
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                # Stat summary
                st.subheader("📊 Estadísticas de Conversión / Metrics Summary")
                col1, col2, col3 = st.columns(3)
                total_tracks = len(results)
                exact_count = sum(1 for r in results if "Exacta" in r["Resultado / Status"])
                similar_count = sum(1 for r in results if "Similares" in r["Resultado / Status"])
                not_found_count = total_tracks - exact_count - similar_count
                
                col1.metric("Canciones Procesadas", total_tracks)
                col2.metric("Exactas / Exact Matches", f"{exact_count} ({round(exact_count/total_tracks*100, 1)}%)" if total_tracks else "0")
                col3.metric("Fuzzy o Búsquedas Directas", f"{similar_count+not_found_count} ({round((similar_count+not_found_count)/total_tracks*100, 1)}%)" if total_tracks else "0")
st.markdown("---")
st.markdown("✨ **SwapUrMusic** | Desarrollado con 💖 en Python con Streamlit.")
