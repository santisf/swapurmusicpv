import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { 
  Music, 
  Search, 
  RefreshCw, 
  CheckCircle, 
  AlertCircle, 
  HelpCircle, 
  Database, 
  ExternalLink, 
  TrendingUp, 
  Heart,
  Chrome,
  Flame,
  Info
} from "lucide-react";

interface Status {
  spotify: boolean;
  youtube: boolean;
  deezer: boolean;
  gemini: boolean;
}

interface TrackMatch {
  song: string;
  artist: string;
  spotifyLink: string;
  youtubeLink: string;
  deezerLink: string;
  matchStatus: string;
  statusClass: string;
  confidenceScore: number;
}

interface ConvertedResponse {
  platform: string;
  mediaType: string;
  results: TrackMatch[];
}

export default function App() {
  const [inputUrl, setInputUrl] = useState("");
  const [sourcePlatform, setSourcePlatform] = useState("Auto-Detect");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultsData, setResultsData] = useState<ConvertedResponse | null>(null);
  
  // Configuration Status Tracker
  const [config, setConfig] = useState<Status>({
    spotify: false,
    youtube: false,
    deezer: true,
    gemini: false
  });

  // Loading quotes
  const loadingQuotes = [
    "Decrypting source URL catalog headers...",
    "Retrieving original track items metadata...",
    "Querying Deezer API data clusters...",
    "Checking YouTube search indices...",
    "Contacting Spotify developer endpoint nodes...",
    "Analyzing track titles and artist strings...",
    "Applying fuzzy Levenshtein token sorted ratios...",
    "Calculating native Gemini semantic vectors...",
    "Aligning remix, live, and acoustic alternate versions...",
    "Consolidating results across three databases..."
  ];
  const [loadingQuoteIndex, setLoadingQuoteIndex] = useState(0);

  // Fetch configuration status
  useEffect(() => {
    fetch("/api/config-status")
      .then(res => res.json())
      .then((data: Status) => setConfig(data))
      .catch(err => console.error("Error fetching config status:", err));
  }, []);

  // Loading quote rotator
  useEffect(() => {
    let interval: any;
    if (isLoading) {
      interval = setInterval(() => {
        setLoadingQuoteIndex(prev => (prev + 1) % loadingQuotes.length);
      }, 2500);
    } else {
      setLoadingQuoteIndex(0);
    }
    return () => clearInterval(interval);
  }, [isLoading]);

  const handleConvert = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputUrl) {
      setError("Please fill out a valid URL first.");
      return;
    }

    setIsLoading(true);
    setError(null);
    setResultsData(null);

    try {
      const response = await fetch("/api/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: inputUrl, sourcePlatform })
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "An error occurred while matching songs");
      }

      setResultsData(data);
    } catch (err: any) {
      setError(err?.message || "Failed to establish server connection");
    } finally {
      setIsLoading(false);
    }
  };

  // Score statistics calculators
  const getTotalTracks = () => resultsData?.results.length || 0;
  const getExactMatches = () => resultsData?.results.filter(r => r.statusClass === "Exact").length || 0;
  const getSimilarMatches = () => resultsData?.results.filter(r => r.statusClass === "Similar").length || 0;
  const getNotFoundMatches = () => getTotalTracks() - getExactMatches() - getSimilarMatches();

  return (
    <div id="swapurmusic-root" className="min-h-screen bg-slate-950 text-slate-200 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      
      {/* HEADER SECTION */}
      <header className="h-16 border-b border-slate-800 flex items-center bg-slate-900/50 backdrop-blur-md sticky top-0 z-30 px-4 sm:px-8">
        <div className="max-w-7xl w-full mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white shadow-md shadow-indigo-600/30">
              <Music className="w-5 h-5 font-bold" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-indigo-400 to-cyan-400 bg-clip-text text-transparent flex items-center gap-2">
                SwapUrMusic <span className="text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-2 py-0.5 rounded-full font-medium">Full Stack Web</span>
              </h1>
            </div>
          </div>
          
          <div className="flex items-center gap-2 sm:gap-3">
            <span className="text-xs text-slate-400 hidden sm:inline">Active Services:</span>
            <div className="flex items-center gap-1.5 bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800">
              <span className={`w-1.5 h-1.5 rounded-full ${config.spotify ? "bg-emerald-500" : "bg-orange-500"}`} />
              <span className="text-[10px] font-medium text-slate-300">Spotify</span>
            </div>
            <div className="flex items-center gap-1.5 bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800">
              <span className={`w-1.5 h-1.5 rounded-full ${config.youtube ? "bg-emerald-500" : "bg-orange-500"}`} />
              <span className="text-[10px] font-medium text-slate-300">YouTube</span>
            </div>
            <div className="flex items-center gap-1.5 bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="text-[10px] font-medium text-slate-300">Deezer</span>
            </div>
            <div className="flex items-center gap-1.5 bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800">
              <span className={`w-1.5 h-1.5 rounded-full ${config.gemini ? "bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)]" : "bg-slate-600"}`} />
              <span className="text-[10px] font-medium text-slate-300">Gemini-AI</span>
            </div>
          </div>
        </div>
      </header>

      {/* MAIN CONTAINER */}
      <main className="max-w-7xl w-full mx-auto px-4 py-8 flex-1 grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* LEFT COLUMN: CONTROL & SETTINGS (4 Cols) */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          
          {/* CONTROL INTERFACE CARD */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Database className="w-4 h-4 text-indigo-400" /> Convert URL
            </h2>
            
            <form onSubmit={handleConvert} className="flex flex-col gap-5">
              
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                    Paste Song or Playlist URL
                  </label>
                  <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 gap-1">
                    <span className="px-2 py-0.5 text-[9px] font-semibold rounded text-slate-300 bg-slate-900 border border-slate-800">Spotify</span>
                    <span className="px-2 py-0.5 text-[9px] font-semibold rounded text-slate-500">YouTube</span>
                    <span className="px-2 py-0.5 text-[9px] font-semibold rounded text-slate-500">Deezer</span>
                  </div>
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                    <Search className="w-4 h-4" />
                  </div>
                  <input
                    type="url"
                    id="music-url-input"
                    value={inputUrl}
                    onChange={(e) => setInputUrl(e.target.value)}
                    placeholder="Spotify, YouTube, or Deezer..."
                    className="w-full bg-slate-950 text-white rounded-xl pl-9 pr-4 py-3 placeholder-slate-500 text-sm border border-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-400 transition-all text-slate-300"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wide">
                  Source Platform
                </label>
                <select
                  id="source-platform-select"
                  value={sourcePlatform}
                  onChange={(e) => setSourcePlatform(e.target.value)}
                  className="w-full bg-slate-950 text-white rounded-xl px-3 py-3 text-sm border border-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-400 transition-all cursor-pointer text-slate-300"
                >
                  <option value="Auto-Detect">🔍 Auto-Detect Platform</option>
                  <option value="Spotify">🟢 Spotify</option>
                  <option value="YouTube Music">🔴 YouTube Music</option>
                  <option value="Deezer">🔵 Deezer</option>
                </select>
              </div>

              <button
                type="submit"
                id="convert-submit-button"
                disabled={isLoading}
                className="w-full bg-indigo-600 hover:bg-indigo-505 text-white font-semibold py-3.5 px-4 rounded-xl shadow-lg shadow-indigo-900/20 active:scale-[0.98] transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 font-sans"
              >
                {isLoading ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" /> Matching Catalog...
                  </>
                ) : (
                  <>
                    <span>Sync Library</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"></path></svg>
                  </>
                )}
              </button>
            </form>
          </div>

          {/* STREAMLIT CLONE INFO BAR */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5 text-slate-400" /> Python Streamlit Output
            </h3>
            <p className="text-xs text-slate-300 leading-relaxed mb-4">
              All backend services have matching local Python files generated! Run SwapUrMusic as a Streamlit application on your device by using:
            </p>
            <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono text-[11px] text-indigo-400 flex justify-between items-center select-all">
              <span>streamlit run main.py</span>
            </div>
            <div className="mt-4 pt-4 border-t border-slate-800 flex flex-col gap-2">
              <span className="text-[10px] text-slate-500 font-semibold uppercase">Files Generated in Workspace:</span>
              <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400">
                <span className="text-emerald-400">📄 main.py</span>
                <span>📂 services/</span>
                <span>📄 requirements.txt</span>
                <span>📂 utils/</span>
              </div>
            </div>
          </div>

          {/* API CONFIGURATION INSTRUCTIONS */}
          <div className="bg-slate-900/50 border border-slate-800/80 rounded-2xl p-5 text-xs text-slate-400 flex flex-col gap-3">
            <span className="font-semibold text-slate-300 uppercase tracking-wide text-[10px]">API Key Status & Instructions:</span>
            <p className="leading-snug">
              Deezer matches work out-of-the-box using the public endpoints. Spotify and YouTube Music conversions will leverage seamless mock search query redirection if no credentials are configured.
            </p>
            <p className="leading-snug">
              For active APIs matching, save keys under <b className="text-slate-300">Settings &gt; Secrets</b> or in your <b className="text-slate-300">.env</b> matching layout:
            </p>
            <ul className="list-disc pl-4 space-y-1 text-slate-500 font-mono text-[10px]">
              <li>SPOTIFY_CLIENT_ID</li>
              <li>SPOTIFY_CLIENT_SECRET</li>
              <li>YOUTUBE_API_KEY</li>
            </ul>
          </div>

        </div>

        {/* RIGHT COLUMN: RESULTS & OUTPUTS (8 Cols) */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          
          {/* INITIAL STATE DISPLAY (IF NO DATA & NO LOADING) */}
          <AnimatePresence mode="wait">
            {!isLoading && !resultsData && !error && (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex-1 flex flex-col items-center justify-center p-8 bg-slate-900/40 border border-slate-800/60 rounded-2xl text-center min-h-[400px]"
              >
                <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center border border-slate-700 text-indigo-400 mb-4 animate-bounce">
                  <Music className="w-6 h-6" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">No Music URL Loaded Yet</h3>
                <p className="text-slate-400 text-sm max-w-sm mb-6">
                  Paste a link from Spotify, Youtube Music, or Deezer on the left to resolve and translate tracks globally.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full max-w-md">
                  <div 
                    onClick={() => setInputUrl("https://open.spotify.com/track/4PTG3Z6ehGkBF3zIqYQGS3")}
                    className="p-3 bg-slate-900 rounded-xl border border-slate-800 text-xs hover:border-slate-700 cursor-pointer transition-all hover:bg-slate-850 text-slate-300 font-medium"
                  >
                    🚀 Try Track url
                  </div>
                  <div 
                    onClick={() => setInputUrl("https://www.deezer.com/playlist/7881021")}
                    className="p-3 bg-slate-900 rounded-xl border border-slate-800 text-xs hover:border-slate-700 cursor-pointer transition-all hover:bg-slate-850 text-slate-300 font-medium"
                  >
                    ⚡ Try Playlist url
                  </div>
                  <div 
                    onClick={() => setInputUrl("https://music.youtube.com/watch?v=dQw4w9WgXcQ")}
                    className="p-3 bg-slate-900 rounded-xl border border-slate-800 text-xs hover:border-slate-700 cursor-pointer transition-all hover:bg-slate-850 text-slate-300 font-medium"
                  >
                    🎵 Rick Astley url
                  </div>
                </div>
              </motion.div>
            )}

            {/* ERROR CARD */}
            {error && (
              <motion.div 
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="p-5 bg-red-950/40 border border-red-500/20 text-red-300 rounded-2xl flex items-start gap-4"
              >
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-white mb-1">Conversion Operation Failed</h4>
                  <p className="text-xs text-red-200/90 leading-relaxed mb-3">{error}</p>
                  <p className="text-[10px] text-red-400">
                    💡 If Spotify/Youtube APIs returned an error, verify your credentials. If you have no keys, we will fall back gracefully to open lookup!
                  </p>
                </div>
              </motion.div>
            )}

            {/* LOADING SCREEN CONTAINER */}
            {isLoading && (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex-1 flex flex-col items-center justify-center p-8 bg-slate-900/40 border border-slate-800/60 rounded-2xl min-h-[400px]"
              >
                <div className="relative mb-6">
                  <div className="w-14 h-14 rounded-full border-2 border-slate-800 border-t-indigo-400 animate-spin" />
                  <div className="absolute inset-0 flex items-center justify-center text-indigo-400">
                    <Flame className="w-5 h-5 animate-pulse" />
                  </div>
                </div>
                
                <h3 className="text-base font-semibold text-white mb-1">Applying Hybrid Vector Metrics</h3>
                <p className="text-slate-400 text-xs text-center max-w-sm h-10 mb-4 animate-pulse">
                  {loadingQuotes[loadingQuoteIndex]}
                </p>
                <div className="w-48 bg-slate-800 h-1 rounded-full overflow-hidden">
                  <div className="bg-indigo-500 h-full w-2/3 animate-[loading_1.5s_infinite_ease-in-out]" />
                </div>
              </motion.div>
            )}

            {/* CONVERTED RESULTS PANEL */}
            {resultsData && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col gap-6"
              >
                
                {/* STATISTICS CARD GRID */}
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                  
                  <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col gap-1">
                    <span className="text-[10px] uppercase font-bold tracking-widest text-slate-400">Total Tracks</span>
                    <span className="text-2xl font-bold font-mono text-white">{getTotalTracks()}</span>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col gap-1">
                    <span className="text-[10px] uppercase font-bold tracking-widest text-emerald-400">Exact Matches</span>
                    <span className="text-2xl font-bold font-mono text-emerald-400">
                      {getExactMatches()} <span className="text-xs font-normal text-slate-400 font-sans">({getTotalTracks() ? Math.round(getExactMatches()/getTotalTracks()*100) : 0}%)</span>
                    </span>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col gap-1">
                    <span className="text-[10px] uppercase font-bold tracking-widest text-amber-400">Fuzzy Matches</span>
                    <span className="text-2xl font-bold font-mono text-amber-500">
                      {getSimilarMatches()} <span className="text-xs font-normal text-slate-400 font-sans">({getTotalTracks() ? Math.round(getSimilarMatches()/getTotalTracks()*100) : 0}%)</span>
                    </span>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col gap-1">
                    <span className="text-[10px] uppercase font-bold tracking-widest text-slate-400">Not Matched</span>
                    <span className="text-2xl font-bold font-mono text-slate-400">
                      {getNotFoundMatches()}
                    </span>
                  </div>

                </div>

                {/* THE RESULTS TABLE */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl flex flex-col">
                  <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
                    <div>
                      <h2 className="text-sm font-semibold text-slate-300">Conversion Results <span className="ml-2 text-xs font-normal text-slate-500">{getTotalTracks()} tracks found</span></h2>
                      <p className="text-[10px] text-slate-500 mt-0.5">Matched using 0.7 * Fuzzy + 0.3 * Gemini AI similarity</p>
                    </div>
                    <span className="text-xs bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800 text-indigo-400 font-mono">
                      Source: {resultsData.platform} ({resultsData.mediaType})
                    </span>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm border-collapse min-w-[900px]">
                      <thead className="text-xs text-slate-500 uppercase font-mono bg-slate-950/50">
                        <tr>
                          <th className="px-6 py-3 font-medium">Song</th>
                          <th className="px-6 py-3 font-medium">Artist</th>
                          <th className="px-6 py-3 font-medium">Spotify Link</th>
                          <th className="px-6 py-3 font-medium">YouTube Link</th>
                          <th className="px-6 py-3 font-medium">Deezer Link</th>
                          <th className="px-6 py-3 font-medium text-center">Match Status</th>
                          <th className="px-6 py-3 font-medium text-right">Conf. Score</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800 text-slate-200">
                        {resultsData.results.map((track, idx) => (
                          <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                            <td className="px-6 py-4 font-medium text-slate-200 max-w-xs truncate">{track.song}</td>
                            <td className="px-6 py-4 text-slate-400 truncate max-w-[150px]">{track.artist}</td>
                            
                            {/* Spotify Link Column */}
                            <td className="px-6 py-4">
                              {track.spotifyLink !== "N/A" ? (
                                <a
                                  href={track.spotifyLink}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400 hover:bg-emerald-500/20 font-medium transition-all"
                                >
                                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                                  Listen / Open
                                </a>
                              ) : (
                                <span className="text-slate-600 font-mono text-xs">—</span>
                              )}
                            </td>

                            {/* YouTube Link Column */}
                            <td className="px-6 py-4">
                              {track.youtubeLink !== "N/A" ? (
                                <a
                                  href={track.youtubeLink}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400 hover:bg-red-500/20 font-medium transition-all"
                                >
                                  <span className="w-2 h-2 rounded-full bg-red-500"></span>
                                  Listen / Open
                                </a>
                              ) : (
                                <span className="text-slate-600 font-mono text-xs">—</span>
                              )}
                            </td>

                            {/* Deezer Link Column */}
                            <td className="px-6 py-4">
                              {track.deezerLink !== "N/A" ? (
                                <a
                                  href={track.deezerLink}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-xs text-cyan-400 hover:bg-cyan-500/20 font-medium transition-all"
                                >
                                  <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                                  Listen / Open
                                </a>
                              ) : (
                                <span className="text-slate-600 font-mono text-xs">—</span>
                              )}
                            </td>

                            {/* Match Status Badge */}
                            <td className="px-6 py-4 text-center whitespace-nowrap">
                              <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
                                track.statusClass === "Exact" 
                                  ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                                  : track.statusClass === "Similar"
                                  ? "bg-amber-500/10 text-amber-500 border-amber-500/20"
                                  : "bg-slate-800 text-slate-500 border-slate-700"
                              }`}>
                                {track.statusClass === "Exact" ? "Exact Match" : track.statusClass === "Similar" ? "Similar" : "Not Found"}
                              </span>
                            </td>

                            {/* Confidence Score Cell */}
                            <td className="px-6 py-4 text-right font-mono text-indigo-400 text-sm">
                              {track.confidenceScore.toFixed(2)}
                            </td>

                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

              </motion.div>
            )}
          </AnimatePresence>

        </div>

      </main>

      {/* FOOTER */}
      <footer className="h-12 border-t border-slate-800 bg-slate-900 px-8 flex items-center justify-between text-xs text-slate-500 mt-12">
        <div className="flex gap-4">
          <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Hybrid Scoring Active</span>
          <span className="text-[10px] font-mono text-slate-500">|</span>
          <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">CPU-ONLY INFERENCE</span>
        </div>
        <p className="text-[10px] text-slate-600 font-medium italic">v1.2.0 stable – Developed for local deployment</p>
      </footer>

    </div>
  );
}
