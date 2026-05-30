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
    
    /* Elegant Title and Header styling */
    .main-title {
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(135deg, #a855f7 0%, #3b82f6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .main-subtitle {
        font-size: 1.15rem;
        color: #94a3b8;
        text-align: center;
        margin-bottom: 2.5rem;
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
st.markdown("<h1 class='main-title'>🎵 SwapUrMusic</h1>", unsafe_allow_html=True)
st.markdown("<p class='main-subtitle'>Convierte y comparte tus canciones y listas de reproducción al instante / Match and swap your music links</p>", unsafe_allow_html=True)

# Main Form Container (Card design)
st.markdown("<div class='input-card'>", unsafe_allow_html=True)

input_url = st.text_input(
    "💡 Enlace de canción o Playlist / Song or Playlist Link:", 
    placeholder="Pega un enlace de Spotify, YouTube o Deezer..."
)

source_platform = st.selectbox(
    "Plataforma de Origen / Source Platform:",
    ["Detectar Automáticamente (Recomendado)", "Spotify", "YouTube Music", "Deezer"]
)

st.markdown("<div style='margin-top: 1.5rem;'>", unsafe_allow_html=True)
convert_btn = st.button("🚀 Convertir Enlace / Convert Link", use_container_width=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True) # Close input-card

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
            st.error("Formato de URL no reconocido. Asegúrate de copiar un enlace de canción (track) or lista de reproducción (playlist) válido.")
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
                    st.error(f"Error cargando metadatos originales: {ex}")
                    tracks_to_match = []

            if tracks_to_match:
                # ====== RENDER TRAC CARD (SINGLE TRACK CONVERSION) ======
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
                        # Get Spotify target
                        if detected_platform != "Spotify":
                            candidates = spotify_service.search_track(title, artist)
                            best_cand, score, _ = matcher.find_best_match(title, artist, candidates)
                            if best_cand:
                                sp_link = best_cand["url"]
                                matched_scores.append(score)
                                
                        # Get YouTube Music target
                        if detected_platform != "YouTube Music":
                            candidates = youtube_service.search_track(title, artist)
                            best_cand, score, _ = matcher.find_best_match(title, artist, candidates)
                            if best_cand:
                                yt_link = best_cand["url"]
                                matched_scores.append(score)
                                
                        # Get Deezer target
                        if detected_platform != "Deezer":
                            candidates = deezer_service.search_track(title, artist)
                            best_cand, score, _ = matcher.find_best_match(title, artist, candidates)
                            if best_cand:
                                dz_link = best_cand["url"]
                                matched_scores.append(score)

                    # Dynamic search backup construction
                    encoded_query = urllib.parse.quote(f"{artist} {title}")
                    if sp_link == "N/A":
                        sp_link = f"https://open.spotify.com/search/{encoded_query}"
                    if yt_link == "N/A":
                        yt_link = f"https://music.youtube.com/search?q={encoded_query}"
                    if dz_link == "N/A":
                        dz_link = f"https://www.deezer.com/search/{encoded_query}"

                    # Compute matching quality
                    avg_score = sum(matched_scores) / len(matched_scores) if matched_scores else 1.0
                    if avg_score >= 0.85:
                        qual_col = "🟢 Coincidencia Exacta / High Accuracy"
                    elif avg_score >= 0.60:
                        qual_col = "🟡 Coincidencia Cercana / Check Match"
                    else:
                        qual_col = "🔵 Búsqueda Directa Fallback / Search Query Link"

                    # Beautiful single card display
                    st.markdown(f"""
                    <div class='track-result-card'>
                        <div style='font-size: 3rem; margin-bottom: 0.5rem;'>🎵</div>
                        <div class='track-title'>{title}</div>
                        <div class='track-artist'>{artist}</div>
                        <div style='margin-bottom: 2rem;'>
                            <span class='badge-platforms'>{qual_col} (Confianza: {int(avg_score * 100)}%)</span>
                        </div>
                        
                        <div class='platform-link-container'>
                            <a href='{sp_link}' target='_blank' class='platform-btn btn-spotify'>
                                <span class='btn-text'>🟢 Escuchar en Spotify</span>
                                <span class='badge-platforms'>ABRIR / OPEN</span>
                            </a>
                            <a href='{yt_link}' target='_blank' class='platform-btn btn-youtube'>
                                <span class='btn-text'>🔴 Escuchar en YouTube Music</span>
                                <span class='badge-platforms'>ABRIR / OPEN</span>
                            </a>
                            <a href='{dz_link}' target='_blank' class='platform-btn btn-deezer btn-deezer-actual'>
                                <span class='btn-text'>🎵 Escuchar en Deezer</span>
                                <span class='badge-platforms'>ABRIR / OPEN</span>
                            </a>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
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
                            "Spotify Link": "N/A",
                            "YouTube Link": "N/A",
                            "Deezer Link": "N/A",
                            "Resultado / Status": "Exact Match",
                            "Confianza / Match Score": 1.0
                        }
                        
                        p_sp_link, p_yt_link, p_dz_link = "N/A", "N/A", "N/A"
                        scores = []
                        
                        if detected_platform == "Spotify":
                            p_sp_link = track.get("url", "N/A")
                        elif detected_platform == "YouTube Music":
                            p_yt_link = track.get("url", "N/A")
                        elif detected_platform == "Deezer":
                            p_dz_link = track.get("url", "N/A")
                            
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

                        # Backup Search Queries
                        encoded = urllib.parse.quote(f"{p_artist} {p_title}")
                        if p_sp_link == "N/A":
                            p_sp_link = f"https://open.spotify.com/search/{encoded}"
                        if p_yt_link == "N/A":
                            p_yt_link = f"https://music.youtube.com/search?q={encoded}"
                        if p_dz_link == "N/A":
                            p_dz_link = f"https://www.deezer.com/search/{encoded}"

                        row["Spotify Link"] = p_sp_link
                        row["YouTube Link"] = p_yt_link
                        row["Deezer Link"] = p_dz_link
                        
                        mean_score = sum(scores) / len(scores) if scores else 1.0
                        row["Confianza / Match Score"] = round(mean_score, 2)
                        
                        if mean_score >= 0.85:
                            row["Resultado / Status"] = "🟩 Alta Precisión / Exact Match"
                        elif mean_score >= 0.60:
                            row["Resultado / Status"] = "🟨 Intermedio / Fuzzy Match"
                        else:
                            row["Resultado / Status"] = "🟦 Búsqueda Directa"
                            
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
                        use_container_width=True
                    )

# Elegant Footer
st.markdown("""
<div class='custom-footer'>
    <p>✨ <b>SwapUrMusic App</b> • Conversor Offline Inteligente. Desarrollado con 💖 utilizando Python & Streamlit.</p>
</div>
""", unsafe_allow_html=True)
