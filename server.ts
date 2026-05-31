import express from "express";
import path from "path";
import dns from "dns";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI, Type } from "@google/genai";
import dotenv from "dotenv";
import { GoogleAuth } from "google-auth-library";

dotenv.config();

const app = express();
const PORT = 3000;

app.use(express.json());

// Initialize Gemini SDK lazily to ensure it doesn't crash if KEY is missing
let aiClient: GoogleGenAI | null = null;
function getGemini(): GoogleGenAI | null {
  if (!aiClient) {
    const key = process.env.GEMINI_API_KEY;
    if (key && key !== "MY_GEMINI_API_KEY") {
      aiClient = new GoogleGenAI({
        apiKey: key,
        httpOptions: {
          headers: {
            'User-Agent': 'aistudio-build',
          }
        }
      });
    }
  }
  return aiClient;
}

// Lazy initialize GoogleAuth for Application Default Credentials (ADC)
let googleAuth: GoogleAuth | null = null;
function getGoogleAuthClient(): GoogleAuth {
  if (!googleAuth) {
    googleAuth = new GoogleAuth({
      scopes: ["https://www.googleapis.com/auth/youtube.readonly"]
    });
  }
  return googleAuth;
}

// Utility to fetch Bearer Token via ADC, with raw API key as secondary fallback
async function getYouTubeCredentials(): Promise<{ headers?: Record<string, string>; apiKey?: string } | null> {
  try {
    const auth = getGoogleAuthClient();
    const client = await auth.getClient();
    const credentials = await client.getAccessToken();
    if (credentials.token) {
      return {
        headers: {
          "Authorization": `Bearer ${credentials.token}`
        }
      };
    }
  } catch (adcError: any) {
    console.log("ADC YouTube token resolution not available or failed:", adcError.message || adcError);
  }

  const apiKey = process.env.YOUTUBE_API_KEY;
  if (apiKey && apiKey !== "YOUR_YOUTUBE_API_KEY") {
    return { apiKey };
  }

  return null;
}

// Environment Config Check endpoint
app.get("/api/config-status", async (req, res) => {
  let isYtActive = false;
  try {
    const creds = await getYouTubeCredentials();
    isYtActive = creds !== null;
  } catch (err) {
    isYtActive = false;
  }

  res.json({
    spotify: !!(process.env.SPOTIFY_CLIENT_ID && process.env.SPOTIFY_CLIENT_SECRET),
    youtube: isYtActive,
    deezer: true, // Always free and available
    gemini: !!process.env.GEMINI_API_KEY
  });
});

// Helper for Token Sort Ratio
function cleanText(text: string): string {
  if (!text) return "";
  return text
    .replace(/[\(\[][Vv]ideo|[Aa]udio|[Oo]fficial|[Mm]usic|[Vv]ideo\s*[Cc]lip|[Hh]D|[Hh]igh\s*[Dd]efinition|[Rr]emastered|[Rr]emaster|[Ll]ive|[Aa]coustic|[Vv]ersion[\)\]]/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function levenshteinDistance(s1: string, s2: string): number {
  const m = s1.length;
  const n = s2.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));

  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (s1[i - 1] === s2[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1];
      } else {
        dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + 1);
      }
    }
  }
  return dp[m][n];
}

function tokenSortRatio(s1: string, s2: string): number {
  const clean1 = cleanText(s1);
  const clean2 = cleanText(s2);
  if (clean1 === clean2) return 100;

  const tokens1 = clean1.split(" ").sort();
  const tokens2 = clean2.split(" ").sort();

  const sorted1 = tokens1.join(" ");
  const sorted2 = tokens2.join(" ");

  const maxLength = Math.max(sorted1.length, sorted2.length);
  if (maxLength === 0) return 100;

  const dist = levenshteinDistance(sorted1, sorted2);
  return Math.round(((maxLength - dist) / maxLength) * 100);
}

function checkVersionMismatch(title1: string, title2: string): boolean {
  const t1 = title1.toLowerCase();
  const t2 = title2.toLowerCase();
  const keywords = ['remix', 'live', 'acoustic', 'unplugged', 'cover', 'instrumental', 'slowed', 'reverb', 'synthwave', 'demo', 'radio edit'];
  for (const kw of keywords) {
    const has1 = t1.includes(kw);
    const has2 = t2.includes(kw);
    if (has1 !== has2) {
      return true;
    }
  }
  return false;
}

// Spotify Client Credentials flow
let spotifyToken = "";
let spotifyTokenExpiry = 0;

async function getSpotifyToken(): Promise<string> {
  const clientID = process.env.SPOTIFY_CLIENT_ID;
  const clientSecret = process.env.SPOTIFY_CLIENT_SECRET;
  
  if (!clientID || !clientSecret) {
    return "";
  }

  if (spotifyToken && Date.now() < spotifyTokenExpiry) {
    return spotifyToken;
  }

  try {
    const auth = Buffer.from(`${clientID}:${clientSecret}`).toString("base64");
    const response = await fetch("https://accounts.spotify.com/api/token", {
      method: "POST",
      headers: {
        Authorization: `Basic ${auth}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: "grant_type=client_credentials",
    });

    if (!response.ok) {
      throw new Error("Failed to retrieve Spotify access token");
    }

    const data: any = await response.json();
    spotifyToken = data.access_token;
    spotifyTokenExpiry = Date.now() + (data.expires_in - 60) * 1000;
    return spotifyToken;
  } catch (error) {
    console.error("Spotify Token retrieval error:", error);
    return "";
  }
}

// Spotify Search Track
async function searchSpotify(title: string, artist: string): Promise<any[]> {
  const token = await getSpotifyToken();
  if (!token) return [];

  try {
    const cleanTitle = title.replace(/[\(\[][Oo]fficial[\s\w]*[\)\]]/gi, "").trim();
    let cleanArtist = artist.replace(/ - Topic$/i, "").trim();
    
    // Split artists to find the primary artist (handles multiple artists separated by comma, ampersand, feat., etc.)
    const artistsList = cleanArtist.split(/[,&]|\bfeat\.?\b|\band\b/i).map(s => s.trim()).filter(Boolean);
    const primaryArtist = artistsList[0] || "";

    const strategies = [
      primaryArtist ? `track:"${cleanTitle}" artist:"${primaryArtist}"` : null,
      cleanArtist && cleanArtist !== primaryArtist ? `track:"${cleanTitle}" artist:"${cleanArtist}"` : null,
      primaryArtist ? `${primaryArtist} ${cleanTitle}` : null,
      artistsList.length > 0 ? `${artistsList.join(" ")} ${cleanTitle}` : null,
      cleanTitle
    ].filter(Boolean) as string[];

    let tracks: any[] = [];
    for (const query of strategies) {
      const response = await fetch(`https://api.spotify.com/v1/search?q=${encodeURIComponent(query)}&type=track&limit=5`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const data: any = await response.json();
        const results = data?.tracks?.items || [];
        if (results.length > 0) {
          tracks = results;
          break; // Stop at first successful strategy
        }
      }
    }

    return tracks.map((t: any) => ({
      title: t.name,
      artist: t.artists.map((a: any) => a.name).join(", "),
      url: `https://open.spotify.com/track/${t.id}`
    }));
  } catch (error) {
    console.error("Spotify search error:", error);
    return [];
  }
}

// Robust helper to extract parsed song title and artist from oEmbed title strings
function parseSongAndArtistFromTitle(titleText: string, oembedAuthor?: string): { title: string; artist: string } {
  let title = titleText.trim();
  let artist = oembedAuthor ? oembedAuthor.trim() : "Unknown Artist";

  // Case 1: Has hyphen + song/cancion + by/de, e.g. "Bodybag - canción de Lil Lotus, Cold Hart" or "Bodybag - song by Lil Lotus"
  const hyphenByMatch = title.match(/^(.*?)\s*-\s*(?:song|canción|cancion|track)?\s*(?:by|de)\s+(.+)$/i);
  if (hyphenByMatch) {
    title = hyphenByMatch[1].trim();
    artist = hyphenByMatch[2].trim();
  } else {
    // Case 2: No hyphen but has song/cancion/by/de, e.g. "By My Side by Anjunabeats"
    // We match from the right to avoid splitting "By My Side" at the first "By"
    const lastByIdx = title.toLowerCase().lastIndexOf(" by ");
    const lastDeIdx = title.toLowerCase().lastIndexOf(" de ");
    const idx = Math.max(lastByIdx, lastDeIdx);
    
    if (idx !== -1) {
      const keywordLen = 4; // both " by " and " de " are 4 characters inclusive of spaces
      const possibleArtist = title.substring(idx + keywordLen).trim();
      const possibleTitle = title.substring(0, idx).trim();
      
      // Clean up possibleTitle from ending "- song" or similar
      const cleanedTitle = possibleTitle.replace(/\s*-\s*(?:song|canción|cancion|lyrics|single|ep|track|video|audio)\s*$/gi, "").trim();
      
      title = cleanedTitle;
      artist = possibleArtist;
    } else if (title.includes(" - ")) {
      // Case 3: Simple hyphen split fallback
      const parts = title.split(" - ");
      if (oembedAuthor && parts[0].toLowerCase().includes(oembedAuthor.toLowerCase())) {
        artist = parts[0].trim();
        title = parts[1].trim();
      } else if (oembedAuthor && parts[1].toLowerCase().includes(oembedAuthor.toLowerCase())) {
        title = parts[0].trim();
        artist = parts[1].trim();
      } else {
        // By default, assume Artist - Title
        artist = parts[0].trim();
        title = parts[1].trim();
      }
    }
  }

  // Final cleanup of title and artist
  artist = artist.replace(/ - Topic$/i, "").trim();
  title = title.replace(/[\(\[][Oo]fficial[\s\w]*[\)\]]/gi, "").trim();
  
  return { title, artist };
}

// Spotify details retrieval
async function getSpotifyTrackMetadata(trackId: string): Promise<any> {
  const token = await getSpotifyToken();
  if (token) {
    try {
      const response = await fetch(`https://api.spotify.com/v1/tracks/${trackId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const data: any = await response.json();
        return {
          title: data.name,
          artist: data.artists.map((a: any) => a.name).join(", "),
          url: `https://open.spotify.com/track/${trackId}`
        };
      }
    } catch (err) {
      console.warn("Spotify API track lookup failed, trying fallback...", err);
    }
  }

  // Fallback 1: Direct HTML scraping of the public Spotify page.
  // Googlebot User-Agent ensures that Spotify returns pre-rendered SEO metadata tags (og:title / og:description / title).
  try {
    const trackUrl = `https://open.spotify.com/track/${trackId}`;
    const response = await fetch(trackUrl, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Accept-Language": "en-US,en;q=0.9"
      }
    });
    if (response.ok) {
      const html = await response.text();
      
      const titleMatch = html.match(/<meta\s+property=["']og:title["']\s+content=["']([^"']+)["']/i) ||
                         html.match(/<meta\s+content=["']([^"']+)["']\s+property=["']og:title["']/i);
      const descMatch = html.match(/<meta\s+property=["']og:description["']\s+content=["']([^"']+)["']/i) ||
                        html.match(/<meta\s+content=["']([^"']+)["']\s+property=["']og:description["']/i);

      let title = "";
      let artist = "";

      if (titleMatch) {
        let rawOgTitle = titleMatch[1].trim();
        // Remove "Spotify" if it was included in og:title
        rawOgTitle = rawOgTitle.replace(/\s*\|\s*Spotify/i, "").replace(/\s*-\s*Spotify/i, "").trim();
        const parsedOg = parseSongAndArtistFromTitle(rawOgTitle);
        title = parsedOg.title;
        artist = parsedOg.artist !== "Unknown Artist" ? parsedOg.artist : "";
      }

      if (descMatch) {
        let desc = descMatch[1].trim();
        
        // Remove language-specific introductory sentence prefixes (e.g. "Listen to ... on Spotify.", "Escucha ... en Spotify.")
        const spotifyIdx = desc.toLowerCase().indexOf("spotify.");
        if (spotifyIdx !== -1) {
          desc = desc.substring(spotifyIdx + 8).trim(); // Skip "spotify." and following spaces
        }
        
        const parts = desc.split(/\s*·\s*/);
        if (parts.length >= 1 && parts[0].trim()) {
          const possibleArtist = parts[0].trim();
          if (!artist || artist === "Unknown Artist") {
            artist = possibleArtist;
          }
        }
      }

      // Read title tag fallback
      const pageTitleMatch = html.match(/<title>([^<]+)<\/title>/i);
      if (pageTitleMatch) {
        let pTitle = pageTitleMatch[1].trim();
        pTitle = pTitle.replace(/\s*\|\s*Spotify/i, "").replace(/\s*-\s*Spotify/i, "").trim();
        
        const parsedMeta = parseSongAndArtistFromTitle(pTitle, artist);
        if (!title) title = parsedMeta.title;
        if (!artist || artist === "Unknown Artist") artist = parsedMeta.artist;
      }

      if (title && artist && artist !== "Unknown Artist") {
        return {
          title,
          artist,
          url: `https://open.spotify.com/track/${trackId}`
        };
      }
    }
  } catch (err: any) {
    console.warn("Direct Spotify HTML scraper fallback failed:", err.message);
  }

  // Fallback 2: Official OEmbed API (very lightweight and fast)
  let oEmbedResult: any = null;
  try {
    const oEmbedRes = await fetch(`https://open.spotify.com/oembed?url=https://open.spotify.com/track/${trackId}`);
    if (oEmbedRes.ok) {
      const odata: any = await oEmbedRes.json();
      if (odata.title) {
        const parsedMeta = parseSongAndArtistFromTitle(odata.title, odata.author_name);
        oEmbedResult = {
          title: parsedMeta.title,
          artist: parsedMeta.artist,
          url: `https://open.spotify.com/track/${trackId}`
        };
        // If we successfully got a real artist, return immediately
        if (oEmbedResult.artist && oEmbedResult.artist !== "Unknown Artist") {
          return oEmbedResult;
        }
      }
    }
  } catch (err: any) {
    console.warn("Spotify oEmbed track fallback failed:", err.message);
  }

  // Fallback 3: Embed Page Scraping + Gemini Parsing
  try {
    const embedUrl = `https://open.spotify.com/embed/track/${trackId}`;
    const response = await fetch(embedUrl, {
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36" }
    });
    if (response.ok) {
      const html = await response.text();
      const gemini = getGemini();
      if (gemini) {
        // Strip heavy styles and svgs to avoid hitting developer token limits
        const bodyContent = html
          .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
          .replace(/<svg[^>]*>[\s\S]*?<\/svg>/gi, "")
          .replace(/path\s+[^>]+/gi, "")
          .substring(0, 15000);

        const prompt = `Extract the music track metadata (Song title and Artist(s)) from this Spotify Embed HTML:
---
${bodyContent}
---
Return ONLY a JSON block matching this schema:
{
  "title": "Song Title",
  "artist": "Artist Name"
}`;
        const modelRes = await gemini.models.generateContent({
          model: "gemini-3.5-flash",
          contents: prompt,
          config: {
            responseMimeType: "application/json",
            responseSchema: {
              type: Type.OBJECT,
              properties: {
                title: { type: Type.STRING },
                artist: { type: Type.STRING }
              },
              required: ["title", "artist"]
                }
              }
            });
        const resText = modelRes.text?.trim() || "{}";
        const info = JSON.parse(resText);
        if (info.title && info.artist && info.artist !== "Unknown Artist") {
          return {
            title: info.title,
            artist: info.artist,
            url: `https://open.spotify.com/track/${trackId}`
          };
        }
      }
    }
  } catch (err: any) {
    console.error("Spotify embed scraping fallback failed for track:", err.message);
  }

  // Fallback 4: If direct, oEmbed, and Gemini all failed or could only partially resolve, return oEmbedResult
  if (oEmbedResult) {
    return oEmbedResult;
  }

  throw new Error("Could not retrieve Spotify track details. No API credentials configured and public lookups failed.");
}

async function getSpotifyPlaylistMetadata(playlistId: string): Promise<any[]> {
  const token = await getSpotifyToken();
  if (token) {
    try {
      const tracks: any[] = [];
      let url = `https://api.spotify.com/v1/playlists/${playlistId}/tracks?limit=50`;
      
      while (url && tracks.length < 100) {
        const response = await fetch(url, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (response.ok) {
          const data: any = await response.json();
          const items = data.items || [];
          for (const item of items) {
            if (item.track) {
              tracks.push({
                title: item.track.name,
                artist: item.track.artists.map((a: any) => a.name).join(", "),
                url: `https://open.spotify.com/track/${item.track.id}`
              });
            }
          }
          url = data.next;
        } else {
          break;
        }
      }
      if (tracks.length > 0) {
        return tracks;
      }
    } catch (err) {
      console.warn("Spotify API playlist lookup failed, trying fallback...", err);
    }
  }

  // Fallback 1: Embed Page Scraper with JSON-LD, __NEXT_DATA__, or initial-state JSON
  try {
    const embedUrl = `https://open.spotify.com/embed/playlist/${playlistId}`;
    const response = await fetch(embedUrl, {
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36" }
    });
    if (response.ok) {
      const html = await response.text();
      
      // Look for NEXT_DATA, resource, or any json state script block
      const scriptMatch = html.match(/<script[^>]*id="(?:resource|__NEXT_DATA__)"[^>]*>([\s\S]*?)<\/script>/i) 
                          || html.match(/<script[^>]*type="application\/json"[^>]*>([\s\S]*?)<\/script>/i);
      
      if (scriptMatch) {
        try {
          const parsedJson = JSON.parse(scriptMatch[1]);
          let rawTracks: any[] = [];
          
          const findTracks = (obj: any) => {
            if (!obj || typeof obj !== "object") return;
            if (Array.isArray(obj)) {
              for (const item of obj) {
                if (item && item.track && typeof item.track === "object" && item.track.name) {
                  rawTracks.push(item.track);
                } else if (item && item.name && item.artists && Array.isArray(item.artists)) {
                  rawTracks.push(item);
                } else {
                  findTracks(item);
                }
              }
            } else {
              if (obj.tracks && Array.isArray(obj.tracks)) {
                rawTracks.push(...obj.tracks);
              } else if (obj.tracks && typeof obj.tracks === "object" && Array.isArray(obj.tracks.items)) {
                for (const item of obj.tracks.items) {
                  if (item.track) rawTracks.push(item.track);
                  else if (item.name) rawTracks.push(item);
                }
              } else {
                for (const key of Object.keys(obj)) {
                  findTracks(obj[key]);
                }
              }
            }
          };
          
          findTracks(parsedJson);
          
          if (rawTracks.length > 0) {
            return rawTracks.map((t: any) => ({
              title: t.name,
              artist: Array.isArray(t.artists) ? t.artists.map((a: any) => a.name || a.profile?.name || "Unknown Artist").join(", ") : "Unknown Artist",
              url: t.id ? `https://open.spotify.com/track/${t.id}` : `https://open.spotify.com/search/${encodeURIComponent(t.name)}`
            }));
          }
        } catch (jsonErr) {
          console.warn("Could not parse or traverse Spotify Embed JSON block:", jsonErr);
        }
      }

      // Fallback 2: Strip body and use Gemini to parse listed track elements
      const gemini = getGemini();
      if (gemini) {
        const bodyContent = html
          .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
          .replace(/<svg[^>]*>[\s\S]*?<\/svg>/gi, "")
          .replace(/path\s+[^>]+/gi, "")
          .substring(0, 18000);

        const prompt = `Extract all track items (Song names and their corresponding Artists) listed in this Spotify Embed playlist page:
---
${bodyContent}
---
Return ONLY a JSON array matching this schema:
[
  { "title": "Song Title 1", "artist": "Artist 1" }
]`;
        const modelRes = await gemini.models.generateContent({
          model: "gemini-3.5-flash",
          contents: prompt,
          config: {
            responseMimeType: "application/json",
            responseSchema: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                properties: {
                  title: { type: Type.STRING },
                  artist: { type: Type.STRING }
                },
                required: ["title", "artist"]
              }
            }
          }
        });
        const resText = modelRes.text?.trim() || "[]";
        const list = JSON.parse(resText);
        if (Array.isArray(list) && list.length > 0) {
          return list.map((item: any) => ({
            title: item.title,
            artist: item.artist || "Unknown Artist",
            url: `https://open.spotify.com/search/${encodeURIComponent(`${item.artist || ""} ${item.title}`)}`
          }));
        }
      }
    }
  } catch (err: any) {
    console.error("Spotify playlist fallback scraping failed:", err.message);
  }

  throw new Error("Could not retrieve Spotify playlist details. No API credentials configured and public lookups failed.");
}

// YouTube Search API using ADC/API Key
async function searchYouTube(title: string, artist: string): Promise<any[]> {
  const creds = await getYouTubeCredentials();
  if (creds) {
    try {
      const cleanTitle = title.replace(/[\(\[][Oo]fficial[\s\w]*[\)\]]/gi, "").trim();
      let cleanArtist = artist.replace(/ - Topic$/i, "").trim();
      const artistsList = cleanArtist.split(/[,&]|\bfeat\.?\b|\band\b/i).map(s => s.trim()).filter(Boolean);
      const primaryArtist = artistsList[0] || "";

      const query = primaryArtist ? `${primaryArtist} ${cleanTitle}` : `${cleanArtist} ${cleanTitle}`;
      let url = `https://www.googleapis.com/youtube/v3/search?part=snippet&q=${encodeURIComponent(query)}&type=video&maxResults=5`;
      const headers: Record<string, string> = { "Accept": "application/json" };

      if (creds.apiKey) {
        url += `&key=${creds.apiKey}`;
      } else if (creds.headers) {
        Object.assign(headers, creds.headers);
      }

      const response = await fetch(url, { headers });
      if (response.ok) {
        const data: any = await response.json();
        const items = data.items || [];

        return items.map((item: any) => {
          const vTitle = item.snippet.title;
          // Crude parsing of Artist - Song
          let songTitle = vTitle;
          let songArtist = item.snippet.channelTitle.replace(" - Topic", "");
          if (vTitle.includes("-")) {
            const parts = vTitle.split("-");
            songArtist = parts[0].trim();
            songTitle = parts[1].trim();
          }
          return {
            title: songTitle.replace(/[\(\[][Oo]fficial[\)\]]/gi, '').trim(),
            artist: songArtist,
            url: `https://music.youtube.com/watch?v=${item.id.videoId}`
          };
        });
      } else {
        console.warn(`YouTube v3 search API returned status ${response.status}. Trying public search fallback...`);
      }
    } catch (apiErr: any) {
      console.warn("YouTube search API failed, trying public search fallback...", apiErr.message || apiErr);
    }
  }

  // Fallback to public search scraping
  return searchYouTubePublic(title, artist);
}

// Public scraping fallback for YouTube search tracks
async function searchYouTubePublic(title: string, artist: string): Promise<any[]> {
  try {
    const query = `${artist} ${title}`;
    const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
    const response = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
      }
    });

    if (!response.ok) return [];

    const html = await response.text();
    const candidates: any[] = [];
    const seenIds = new Set<string>();

    const regex = /"videoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"([^"]+)"\}\].*?"ownerText":\{"runs":\[\{"text":"([^"]+)"\}/g;
    let match;
    while ((match = regex.exec(html)) !== null && candidates.length < 5) {
      const videoId = match[1];
      const videoTitle = match[2];
      const videoChannel = match[3];

      if (seenIds.has(videoId)) continue;
      seenIds.add(videoId);

      let songTitle = videoTitle;
      let songArtist = videoChannel.replace(" - Topic", "");
      if (videoTitle.includes("-")) {
        const parts = videoTitle.split("-");
        songArtist = parts[0].trim();
        songTitle = parts[1].trim();
      }

      candidates.push({
        title: songTitle.replace(/[\(\[][Oo]fficial[\)\]]/gi, '').trim(),
        artist: songArtist,
        url: `https://music.youtube.com/watch?v=${videoId}`
      });
    }

    if (candidates.length === 0) {
      const vidRegex = /\/watch\?v=([a-zA-Z0-9_-]{11})/g;
      const uniqueIds: string[] = [];
      let vidMatch;
      while ((vidMatch = vidRegex.exec(html)) !== null && uniqueIds.length < 3) {
        const vid = vidMatch[1];
        if (!seenIds.has(vid)) {
          seenIds.add(vid);
          uniqueIds.push(vid);
        }
      }

      for (const vid of uniqueIds) {
        try {
          const detail = await getYouTubeTrackMetadata(vid);
          if (detail) {
            candidates.push(detail);
          }
        } catch {
          // ignore individual video lookup failures
        }
      }
    }

    return candidates;
  } catch (err: any) {
    console.error("YouTube public search failed:", err.message || err);
    return [];
  }
}

// Retrieve single YouTube video details using ADC/API Key, with oEmbed as a free fallback
async function getYouTubeTrackMetadata(videoId: string): Promise<any> {
  try {
    const creds = await getYouTubeCredentials();
    if (creds) {
      let url = `https://www.googleapis.com/youtube/v3/videos?part=snippet&id=${videoId}`;
      const headers: Record<string, string> = { "Accept": "application/json" };

      if (creds.apiKey) {
        url += `&key=${creds.apiKey}`;
      } else if (creds.headers) {
        Object.assign(headers, creds.headers);
      }

      const response = await fetch(url, { headers });
      if (response.ok) {
        const data: any = await response.json();
        const item = data.items?.[0];
        if (item) {
          const parsedMeta = parseSongAndArtistFromTitle(item.snippet.title, item.snippet.channelTitle);
          return {
            title: parsedMeta.title,
            artist: parsedMeta.artist,
            url: `https://music.youtube.com/watch?v=${videoId}`
          };
        }
      } else {
        console.warn(`YouTube v3 API returned status ${response.status}. Trying oEmbed fallback...`);
      }
    }
  } catch (err: any) {
    console.warn("YouTube v3 API video lookup failed. Trying oEmbed fallback:", err.message || err);
  }

  // Fallback to free, public oEmbed API which requires no credentials or API keys
  try {
    const oEmbedUrl = `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`;
    const response = await fetch(oEmbedUrl);
    if (!response.ok) {
      throw new Error(`oEmbed request failed with status: ${response.status}`);
    }
    const data: any = await response.json();
    const vTitle = data.title || "Unknown YouTube Song";
    const parsedMeta = parseSongAndArtistFromTitle(vTitle, data.author_name);
    return {
      title: parsedMeta.title,
      artist: parsedMeta.artist,
      url: `https://music.youtube.com/watch?v=${videoId}`
    };
  } catch (oEmbedErr: any) {
    console.error("YouTube oEmbed lookup failed too:", oEmbedErr.message || oEmbedErr);
    throw new Error(`YouTube video lookup failed. Both YouTube API/ADC and oEmbed lookup could not resolve video details.`);
  }
}

async function getYouTubePlaylistMetadata(playlistId: string): Promise<any[]> {
  const creds = await getYouTubeCredentials();
  if (creds) {
    try {
      const tracks: any[] = [];
      let pageToken = "";
      let keepFetching = true;

      while (keepFetching && tracks.length < 100) {
        let url = `https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId=${playlistId}&maxResults=50&pageToken=${pageToken}`;
        const headers: Record<string, string> = { "Accept": "application/json" };

        if (creds.apiKey) {
          url += `&key=${creds.apiKey}`;
        } else if (creds.headers) {
          Object.assign(headers, creds.headers);
        }

        const response = await fetch(url, { headers });
        if (!response.ok) {
          throw new Error(`YouTube playlist lookup failed with status: ${response.status}`);
        }

        const data: any = await response.json();
        const items = data.items || [];
        for (const item of items) {
          const vTitle = item.snippet.title;
          const vId = item.snippet.resourceId?.videoId;
          if (vId) {
            let songTitle = vTitle;
            let songArtist = item.snippet.videoOwnerChannelTitle || item.snippet.channelTitle || "Unknown Artist";
            songArtist = songArtist.replace(" - Topic", "");
            if (vTitle.includes("-")) {
              const parts = vTitle.split("-");
              songArtist = parts[0].trim();
              songTitle = parts[1].trim();
            }
            tracks.push({
              title: songTitle.replace(/[\(\[][Oo]fficial[\)\]]/gi, '').trim(),
              artist: songArtist,
              url: `https://music.youtube.com/watch?v=${vId}`
            });
          }
        }
        pageToken = data.nextPageToken;
        keepFetching = !!pageToken;
      }
      return tracks;
    } catch (apiErr: any) {
      console.warn("YouTube API playlist retrieval failed, trying public scraping fallback...", apiErr.message || apiErr);
    }
  }

  // Fallback to public YouTube playlist scraping
  return getYouTubePlaylistMetadataPublic(playlistId);
}

// Public scraping fallback for YouTube playlist tracks
async function getYouTubePlaylistMetadataPublic(playlistId: string): Promise<any[]> {
  try {
    const url = `https://www.youtube.com/playlist?list=${playlistId}`;
    const response = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": "CONSENT=YES+cb.20210328-17-p0.en-GB+FX+999; SOCS=eSG_AgIE"
      }
    });

    if (!response.ok) {
      throw new Error(`Public scraping failed with status: ${response.status}`);
    }

    const html = await response.text();
    const tracks: any[] = [];
    const seenIds = new Set<string>();

    const startKeyword = "ytInitialData = ";
    const startIdx = html.indexOf(startKeyword);
    if (startIdx !== -1) {
      try {
        let endIdx = html.indexOf(";</script>", startIdx);
        if (endIdx === -1) {
          endIdx = html.indexOf("};", startIdx);
        }
        if (endIdx !== -1) {
          let rawJson = html.substring(startIdx + startKeyword.length, endIdx + 1).trim();
          if (rawJson.endsWith(";")) {
            rawJson = rawJson.slice(0, -1);
          }
          const data = JSON.parse(rawJson);

          const recurse = (obj: any) => {
            if (!obj || typeof obj !== "object") return;

            // Handle playlistVideoRenderer
            if (obj.playlistVideoRenderer) {
              const render = obj.playlistVideoRenderer;
              const vId = render.videoId;
              if (vId && !seenIds.has(vId)) {
                seenIds.add(vId);
                const rawTitle = render.title?.runs?.[0]?.text || render.title?.simpleText || "Unknown Title";
                const rawArtist = render.shortBylineText?.runs?.[0]?.text || "Unknown Artist";
                
                let songTitle = rawTitle;
                let songArtist = rawArtist.replace(" - Topic", "");
                if (rawTitle.includes("-")) {
                  const parts = rawTitle.split("-");
                  songArtist = parts[0].trim();
                  songTitle = parts[1].trim();
                }

                tracks.push({
                  title: songTitle.replace(/[\(\[][Oo]fficial[\)\]]/gi, '').trim(),
                  artist: songArtist,
                  url: `https://music.youtube.com/watch?v=${vId}`
                });
              }
            }

            // Handle playlistItemRenderer (frequent for albums)
            if (obj.playlistItemRenderer) {
              const render = obj.playlistItemRenderer;
              const vId = render.videoId;
              if (vId && !seenIds.has(vId)) {
                seenIds.add(vId);
                const rawTitle = render.title?.runs?.[0]?.text || render.title?.simpleText || "Unknown Title";
                const rawArtist = render.shortBylineText?.runs?.[0]?.text || "Unknown Artist";

                let songTitle = rawTitle;
                let songArtist = rawArtist.replace(" - Topic", "");
                if (rawTitle.includes("-")) {
                  const parts = rawTitle.split("-");
                  songArtist = parts[0].trim();
                  songTitle = parts[1].trim();
                }

                tracks.push({
                  title: songTitle.replace(/[\(\[][Oo]fficial[\)\]]/gi, '').trim(),
                  artist: songArtist,
                  url: `https://music.youtube.com/watch?v=${vId}`
                });
              }
            }

            for (const key in obj) {
              if (Object.prototype.hasOwnProperty.call(obj, key) && typeof obj[key] === "object") {
                recurse(obj[key]);
              }
            }
          };

          recurse(data);

          // Looser JSON search if exact items match nothing and we still want to grab tracks
          if (tracks.length === 0) {
            const recurseLoose = (obj: any) => {
              if (!obj || typeof obj !== "object") return;
              if (obj.videoId && obj.title && (obj.title.runs || typeof obj.title === "string")) {
                const vId = obj.videoId;
                if (vId && vId.length === 11 && !seenIds.has(vId)) {
                  seenIds.add(vId);
                  const rawTitle = typeof obj.title === "string" ? obj.title : obj.title?.runs?.[0]?.text || "Unknown Title";
                  const rawArtist = obj.shortBylineText?.runs?.[0]?.text || obj.author || "Unknown Artist";

                  let songTitle = rawTitle;
                  let songArtist = rawArtist.replace(" - Topic", "");
                  if (rawTitle.includes("-")) {
                    const parts = rawTitle.split("-");
                    songArtist = parts[0].trim();
                    songTitle = parts[1].trim();
                  }

                  tracks.push({
                    title: songTitle.replace(/[\(\[][Oo]fficial[\)\]]/gi, '').trim(),
                    artist: songArtist,
                    url: `https://music.youtube.com/watch?v=${vId}`
                  });
                }
              }
              for (const key in obj) {
                if (Object.prototype.hasOwnProperty.call(obj, key) && typeof obj[key] === "object") {
                  recurseLoose(obj[key]);
                }
              }
            };
            recurseLoose(data);
          }
        }
      } catch (parseErr) {
        console.warn("Error parsing public ytInitialData JSON:", parseErr);
      }
    }

    // Fallback to legacy regex checks only if JSON walker found absolutely nothing
    if (tracks.length === 0) {
      const regex = /\{"playlistVideoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"([^"]+)"\}\].*?"shortBylineText":\{"runs":\[\{"text":"([^"]+)"\}/g;
      let match;
      while ((match = regex.exec(html)) !== null && tracks.length < 100) {
        const videoId = match[1];
        const origTitle = match[2];
        const origChannel = match[3];

        if (seenIds.has(videoId)) continue;
        seenIds.add(videoId);

        let songTitle = origTitle;
        let songArtist = origChannel.replace(" - Topic", "");
        if (origTitle.includes("-")) {
          const parts = origTitle.split("-");
          songArtist = parts[0].trim();
          songTitle = parts[1].trim();
        }

        tracks.push({
          title: songTitle.replace(/[\(\[][Oo]fficial[\)\]]/gi, '').trim(),
          artist: songArtist,
          url: `https://music.youtube.com/watch?v=${videoId}`
        });
      }
    }

    if (tracks.length === 0) {
      const simpleRegex = /"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"/g;
      const uniqueVids: string[] = [];
      let simpleMatch;
      while ((simpleMatch = simpleRegex.exec(html)) !== null && uniqueVids.length < 30) {
        const vid = simpleMatch[1];
        if (!seenIds.has(vid)) {
          seenIds.add(vid);
          uniqueVids.push(vid);
        }
      }

      for (const vid of uniqueVids) {
        try {
          const details = await getYouTubeTrackMetadata(vid);
          if (details) {
            tracks.push(details);
          }
        } catch {
          // ignore individual track details failures
        }
      }
    }

    if (tracks.length === 0) {
      throw new Error("Could not find any playlist track list via public scraping.");
    }

    return tracks;
  } catch (err: any) {
    console.error("Public playlist scraping failed:", err.message || err);
    throw new Error(`Failed to fetch YouTube playlist tracks: ${err.message || err}`);
  }
}

// Deezer Endpoint Integrations (Free API!)
async function expandDeezerPageUrl(url: string): Promise<string> {
  if (url.includes("deezer.page.link") || url.includes("deezer.com")) {
    try {
      const res = await fetch(url, { redirect: "follow", method: "GET" });
      return res.url;
    } catch (e) {
      console.error("Deezer url shortener resolution error:", e);
    }
  }
  return url;
}

async function searchDeezer(title: string, artist: string): Promise<any[]> {
  try {
    const cleanTitle = title.replace(/[\(\[][Oo]fficial[\s\w]*[\)\]]/gi, "").trim();
    let cleanArtist = artist.replace(/ - Topic$/i, "").trim();
    
    // Split artists to find the primary artist (handles multiple artists separated by comma, ampersand, feat., etc.)
    const artistsList = cleanArtist.split(/[,&]|\bfeat\.?\b|\band\b/i).map(s => s.trim()).filter(Boolean);
    const primaryArtist = artistsList[0] || "";

    const strategies = [
      primaryArtist ? `track:"${cleanTitle}" artist:"${primaryArtist}"` : null,
      cleanArtist && cleanArtist !== primaryArtist ? `track:"${cleanTitle}" artist:"${cleanArtist}"` : null,
      primaryArtist ? `${primaryArtist} ${cleanTitle}` : null,
      artistsList.length > 0 ? `${artistsList.join(" ")} ${cleanTitle}` : null,
      cleanTitle
    ].filter(Boolean) as string[];

    let items: any[] = [];
    for (const query of strategies) {
      const response = await fetch(`https://api.deezer.com/search?q=${encodeURIComponent(query)}`);
      if (response.ok) {
        const data: any = await response.json();
        const results = data.data || [];
        if (results.length > 0) {
          items = results;
          break; // Stop at first successful query strategy that returns results!
        }
      }
    }

    return items.slice(0, 5).map((item: any) => ({
      title: item.title,
      artist: item.artist.name,
      url: `https://www.deezer.com/track/${item.id}`
    }));
  } catch (error) {
    console.error("Deezer search query failed:", error);
    return [];
  }
}

async function getDeezerTrackMetadata(trackId: string): Promise<any> {
  const response = await fetch(`https://api.deezer.com/track/${trackId}`);
  if (!response.ok) throw new Error("Deezer track details lookup failed.");
  const data: any = await response.json();
  if (data.error) throw new Error(data.error.message || "Deezer API returned an error.");
  return {
    title: data.title,
    artist: data.artist.name,
    url: `https://www.deezer.com/track/${trackId}`
  };
}

async function getDeezerPlaylistMetadata(playlistId: string): Promise<any[]> {
  const response = await fetch(`https://api.deezer.com/playlist/${playlistId}`);
  if (!response.ok) throw new Error("Deezer playlist lookup failed.");
  const data: any = await response.json();
  if (data.error) throw new Error(data.error.message || "Deezer API playlist error.");

  const tracks = data.tracks?.data || [];
  return tracks.map((item: any) => ({
    title: item.title,
    artist: item.artist.name,
    url: `https://www.deezer.com/track/${item.id}`
  }));
}

// Clean matching and scorer
async function calculateBestMatch(
  queryTitle: string,
  queryArtist: string,
  candidates: any[]
): Promise<{ bestCand: any | null; bestScore: number }> {
  if (candidates.length === 0) {
    return { bestCand: null, score: 0 } as any;
  }

  let bestCand: any = null;
  let bestScore = -1;

  // Use Gemini strictly for intelligent semantic alignment, version matching & disambiguation
  const gemini = getGemini();
  const cleanQ = `${cleanText(queryTitle)} ${cleanText(queryArtist)}`;

  // Evaluate candidate scores combining fuzzy and AI logic
  for (const cand of candidates) {
    const cleanCand = `${cleanText(cand.title)} ${cleanText(cand.artist)}`;
    
    // Fuzzy calculation (Token Sort Ratio)
    const fuzzyScore = tokenSortRatio(cleanQ, cleanCand) / 100.0;

    // AI Semantic similarity matching
    let aiScore = fuzzyScore;
    if (gemini) {
      try {
        const prompt = `Match track item attributes representing semantic similarity.
Query: "${queryTitle}" by "${queryArtist}"
Candidate: "${cand.title}" by "${cand.artist}"

Review song name, primary artist, secondary features, and version markers (like Acoustic, Remix, Live, Radio Edit).
If one is a remix or live version and the other is not, the version matching score is strictly 0.
Return only a JSON object matching this schema:
{
  "semanticSimilarity": number (0.0 to 1.0),
  "isVersionMismatch": boolean
}`;
        const modelRes = await gemini.models.generateContent({
          model: "gemini-3.5-flash",
          contents: prompt,
          config: {
            responseMimeType: "application/json",
            responseSchema: {
              type: Type.OBJECT,
              properties: {
                semanticSimilarity: { type: Type.NUMBER },
                isVersionMismatch: { type: Type.BOOLEAN }
              },
              required: ["semanticSimilarity", "isVersionMismatch"]
            }
          }
        });

        const info = JSON.parse(modelRes.text?.trim() || "{}");
        if (info.isVersionMismatch) {
          aiScore = info.semanticSimilarity * 0.4; // Apply heavy penalty
        } else {
          aiScore = info.semanticSimilarity;
        }
      } catch (geminiError) {
        console.error("Gemini math evaluation bypassed:", geminiError);
      }
    }

    // Hybrid calculation: 70% fuzzy sorting + 30% local AI similarity estimation
    let score = 0.7 * fuzzyScore + 0.3 * aiScore;
    
    // Heuristic boost: exact title & primary artist shared (handles features elegantly)
    const qArtistsList = queryArtist.replace(/ - Topic$/i, "").split(/[,&]|\bfeat\.?\b|\band\b/i).map(s => s.trim().toLowerCase()).filter(Boolean);
    const qPrimaryArtist = qArtistsList[0] || "";

    const cArtistsList = cand.artist.replace(/ - Topic$/i, "").split(/[,&]|\bfeat\.?\b|\band\b/i).map(s => s.trim().toLowerCase()).filter(Boolean);
    const cPrimaryArtist = cArtistsList[0] || "";

    const cleanQTitle = cleanText(queryTitle).toLowerCase();
    const cleanCTitle = cleanText(cand.title).toLowerCase();

    if (cleanQTitle === cleanCTitle && cleanQTitle.length > 0) {
      const hasPrimaryArtistMatch = !!(qPrimaryArtist && cPrimaryArtist && (
        qPrimaryArtist === cPrimaryArtist ||
        qArtistsList.includes(cPrimaryArtist) ||
        cArtistsList.includes(qPrimaryArtist)
      ));
      if (hasPrimaryArtistMatch) {
        score = Math.max(score, 0.95);
      }
    }
    
    // Version check fallbacks
    if (checkVersionMismatch(`${queryTitle} ${queryArtist}`, `${cand.title} ${cand.artist}`)) {
      score = score * 0.5;
    }

    if (score > bestScore) {
      bestScore = score;
      bestCand = cand;
    }
  }

  return { bestCand, bestScore };
}

// Extraction parsing helper
function parseMusicUrl(url: string): { platform: string; mediaType: string; id: string } | null {
  if (url.includes("spotify.com")) {
    const trackM = url.match(/spotify\.com\/(?:.*\/)?track\/([a-zA-Z0-9]+)/);
    if (trackM) return { platform: "Spotify", mediaType: "track", id: trackM[1] };
    const playM = url.match(/spotify\.com\/(?:.*\/)?playlist\/([a-zA-Z0-9]+)/);
    if (playM) return { platform: "Spotify", mediaType: "playlist", id: playM[1] };
  } else if (url.includes("youtube.com") || url.includes("youtu.be") || url.includes("music.youtube.com")) {
    let videoId = "";
    let playlistId = "";

    const vMatch = url.match(/(?:youtube\.com|music\.youtube\.com)\/watch\?v=([a-zA-Z0-9_-]+)/);
    if (vMatch) {
      videoId = vMatch[1];
    } else {
      const sMatch = url.match(/youtu\.be\/([a-zA-Z0-9_-]+)/);
      if (sMatch) videoId = sMatch[1];
    }

    const pMatch = url.match(/list=([a-zA-Z0-9_-]+)/);
    if (pMatch) playlistId = pMatch[1];

    if (playlistId && (url.includes("playlist") || !videoId)) {
      return { platform: "YouTube Music", mediaType: "playlist", id: playlistId };
    }
    if (videoId) {
      return { platform: "YouTube Music", mediaType: "track", id: videoId };
    }
  } else if (url.includes("deezer.com") || url.includes("deezer.page.link")) {
    const trackM = url.match(/deezer\.com\/(?:.*\/)?track\/(\d+)/);
    if (trackM) return { platform: "Deezer", mediaType: "track", id: trackM[1] };
    const playM = url.match(/deezer\.com\/(?:.*\/)?playlist\/(\d+)/);
    if (playM) return { platform: "Deezer", mediaType: "playlist", id: playM[1] };
  }
  return null;
}

// CORE MATCH API ROUTE
app.post("/api/convert", async (req, res) => {
  const { url, sourcePlatform } = req.body;
  if (!url) {
    return res.status(400).json({ error: "Source link is required" });
  }

  try {
    const resolvedUrl = await expandDeezerPageUrl(url);
    const parsed = parseMusicUrl(resolvedUrl);
    
    if (!parsed) {
      return res.status(400).json({ error: "Could not parse or recognize the music URL format" });
    }

    let sourceMetadata: any[] = [];
    const sourcePlatformActual = parsed.platform;

    // A: RETRIEVE ORIGINAL OR TRACK LIST METADATA
    if (parsed.mediaType === "track") {
      let meta: any = null;
      if (sourcePlatformActual === "Spotify") {
        meta = await getSpotifyTrackMetadata(parsed.id);
      } else if (sourcePlatformActual === "YouTube Music") {
        meta = await getYouTubeTrackMetadata(parsed.id);
      } else if (sourcePlatformActual === "Deezer") {
        meta = await getDeezerTrackMetadata(parsed.id);
      }
      if (meta) sourceMetadata.push(meta);
    } else {
      // Playlist Type
      if (sourcePlatformActual === "Spotify") {
        sourceMetadata = await getSpotifyPlaylistMetadata(parsed.id);
      } else if (sourcePlatformActual === "YouTube Music") {
        sourceMetadata = await getYouTubePlaylistMetadata(parsed.id);
      } else if (sourcePlatformActual === "Deezer") {
        sourceMetadata = await getDeezerPlaylistMetadata(parsed.id);
      }
    }

    if (sourceMetadata.length === 0) {
      return res.status(404).json({ error: "No tracks resolved from the source URL link" });
    }

    // B: CONVERT AND MATCH TO OTHER TWO PLATFORMS
    const results: any[] = [];
    
    const isSpotifyActive = !!(process.env.SPOTIFY_CLIENT_ID && process.env.SPOTIFY_CLIENT_SECRET);
    const isYouTubeActive = !!(await getYouTubeCredentials());

    for (const track of sourceMetadata) {
      const qTitle = track.title;
      const qArtist = track.artist;
      
      let spLink = "N/A";
      let ytLink = "N/A";
      let dzLink = "N/A";
      const matchScores: number[] = [];

      // Link values for original source
      if (sourcePlatformActual === "Spotify") spLink = track.url || "N/A";
      if (sourcePlatformActual === "YouTube Music") ytLink = track.url || "N/A";
      if (sourcePlatformActual === "Deezer") dzLink = track.url || "N/A";

      // 1. Convert to Spotify if not source
      if (sourcePlatformActual !== "Spotify") {
        if (isSpotifyActive) {
          const cand = await searchSpotify(qTitle, qArtist);
          const { bestCand, bestScore } = await calculateBestMatch(qTitle, qArtist, cand);
          if (bestCand) {
            spLink = bestCand.url;
            matchScores.push(bestScore);
          }
        } else {
          // Public Deezer Match as Fallback URL proxy
          const cand = await searchDeezer(qTitle, qArtist);
          if (cand.length > 0) {
            spLink = `https://open.spotify.com/search/${encodeURIComponent(`${qArtist} ${qTitle}`)}`;
            matchScores.push(0.7); // Fallback match factor
          }
        }
        // Strict guard: if still N/A, provide a clean search query link
        if (spLink === "N/A") {
          spLink = `https://open.spotify.com/search/${encodeURIComponent(`${qArtist} ${qTitle}`)}`;
        }
      }

      // 2. Convert to YouTube Music if not source
      if (sourcePlatformActual !== "YouTube Music") {
        if (isYouTubeActive) {
          const cand = await searchYouTube(qTitle, qArtist);
          const { bestCand, bestScore } = await calculateBestMatch(qTitle, qArtist, cand);
          if (bestCand) {
            ytLink = bestCand.url;
            matchScores.push(bestScore);
          }
        }
        // Strict guard: if still N/A, provide a clean search query link
        if (ytLink === "N/A") {
          ytLink = `https://music.youtube.com/search?q=${encodeURIComponent(`${qArtist} ${qTitle}`)}`;
        }
      }

      // 3. Convert to Deezer if not source
      if (sourcePlatformActual !== "Deezer") {
        const cand = await searchDeezer(qTitle, qArtist);
        const { bestCand, bestScore } = await calculateBestMatch(qTitle, qArtist, cand);
        if (bestCand) {
          dzLink = bestCand.url;
          matchScores.push(bestScore);
        }
        // Strict guard: if still N/A, provide a clean search query link
        if (dzLink === "N/A") {
          dzLink = `https://www.deezer.com/search/${encodeURIComponent(`${qArtist} ${qTitle}`)}`;
        }
      }

      const meanScore = matchScores.length > 0 
        ? matchScores.reduce((a, b) => a + b, 0) / matchScores.length
        : 1.0;

      let status = "🟥 Not Found";
      let statusClass = "Not Found";
      if (meanScore >= 0.85) {
        status = "🟩 Exact Match";
        statusClass = "Exact";
      } else if (meanScore >= 0.60) {
        status = "🟨 Similar Match";
        statusClass = "Similar";
      }

      results.push({
        song: qTitle,
        artist: qArtist,
        spotifyLink: spLink,
        youtubeLink: ytLink,
        deezerLink: dzLink,
        matchStatus: status,
        statusClass: statusClass,
        confidenceScore: parseFloat(meanScore.toFixed(2))
      });
    }

    res.json({
      platform: sourcePlatformActual,
      mediaType: parsed.mediaType,
      results
    });
  } catch (error: any) {
    console.error("Match Conversion error in server route:", error);
    res.status(500).json({ error: error?.message || "Internal server transition errors occurred" });
  }
});

// Configure Vite integration or static delivery
async function startWebBackend() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`SwapUrMusic Full-Stack webserver boot on http://localhost:${PORT}`);
  });
}

startWebBackend();
