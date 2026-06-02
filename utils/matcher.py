import os
import re
import json

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

# Try local sentence-transformers as secondary local AI fallback
try:
    from sentence_transformers import SentenceTransformer, util
    HAS_SENTENCE_TRANSFORMERS = True
except Exception:
    HAS_SENTENCE_TRANSFORMERS = False

# Try Gemini API client as primary serverless AI fallback
HAS_GEMINI = False
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key or gemini_api_key == "MY_GEMINI_API_KEY":
    try:
        import streamlit as st
        if "GEMINI_API_KEY" in st.secrets:
            gemini_api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

if gemini_api_key and gemini_api_key != "MY_GEMINI_API_KEY":
    try:
        # We can support either the modern google-genai or legacy google-generativeai
        try:
            from google import genai
            from google.genai import types
            ai_client = genai.Client(api_key=gemini_api_key)
            USE_NEW_SDK = True
            HAS_GEMINI = True
        except ImportError:
            import google.generativeai as gen_ai
            gen_ai.configure(api_key=gemini_api_key)
            USE_NEW_SDK = False
            HAS_GEMINI = True
    except Exception as e:
        print(f"Failed to initialize Gemini AI Matcher client: {e}")

class Matcher:
    def __init__(self):
        self.model = None
        if HAS_SENTENCE_TRANSFORMERS:
            try:
                # Load specified local model on CPU
                self.model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
            except Exception as e:
                print(f"Warning: SentenceTransformer 'all-MiniLM-L6-v2' could not load: {e}")

    def clean_text(self, text):
        if not text:
            return ""
        # Remove any parentheses/brackets that contain common video/audio metadata tags
        text = re.sub(
            r'[\(\[][^\)\]]*(?:video|audio|official|music|clip|hd|definition|remastered|remaster|lyrics?|version|live|acoustic)[^\)\]]*[\)\]]', 
            '', 
            text, 
            flags=re.IGNORECASE
        )
        # Remove any empty or trailing parentheses/brackets
        text = re.sub(r'\(\s*\)|\[\s*\]', '', text)
        # Clean up multiple whitespaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip().lower()

    def check_version_mismatch(self, title1, title2):
        t1, t2 = title1.lower(), title2.lower()
        keywords = ['remix', 'live', 'acoustic', 'unplugged', 'cover', 'instrumental', 'slowed', 'reverb', 'synthwave', 'demo', 'radio edit']
        for kw in keywords:
            has1 = kw in t1
            has2 = kw in t2
            if has1 != has2:
                return True
        return False

    def levenshtein_distance(self, s1, s2):
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + 1)
        return dp[m][n]

    def token_sort_ratio(self, s1, s2):
        if HAS_RAPIDFUZZ:
            return fuzz.token_sort_ratio(s1, s2)
        
        # Manual fallback token_sort_ratio
        clean1 = self.clean_text(s1)
        clean2 = self.clean_text(s2)
        if clean1 == clean2:
            return 100
        
        t1 = sorted(clean1.split())
        t2 = sorted(clean2.split())
        
        sorted1 = " ".join(t1)
        sorted2 = " ".join(t2)
        
        max_len = max(len(sorted1), len(sorted2))
        if max_len == 0:
            return 100
            
        dist = self.levenshtein_distance(sorted1, sorted2)
        return round(((max_len - dist) / max_len) * 100)

    def compute_score(self, song1, artist1, song2, artist2):
        clean_q = f"{self.clean_text(song1)} {self.clean_text(artist1)}"
        clean_t = f"{self.clean_text(song2)} {self.clean_text(artist2)}"
        
        # 1. Fuzzy score using token sort ratio
        fuzzy_score_val = self.token_sort_ratio(clean_q, clean_t) / 100.0
        
        if clean_q == clean_t:
            fuzzy_score_val = 1.0

        ai_similarity_val = fuzzy_score_val
        
        # 2. AI Semantic Similarity
        # Priority A: Gemini evaluation (lightweight, API based)
        if HAS_GEMINI:
            try:
                prompt = f"""Match track item attributes representing semantic similarity.
Query: "{song1}" by "{artist1}"
Candidate: "{song2}" by "{artist2}"

Review song name, primary artist, secondary features, and version markers (like Acoustic, Remix, Live, Radio Edit).
If one is a remix or live version and the other is not, the version matching score is strictly 0.
Return only a JSON object matching this schema:
{{
  "semanticSimilarity": number (0.0 to 1.0),
  "isVersionMismatch": boolean
}}"""
                if USE_NEW_SDK:
                    res = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    text_out = res.text
                else:
                    model = gen_ai.GenerativeModel('gemini-2.5-flash')
                    res = model.generate_content(
                        prompt,
                        generation_config={"response_mime_type": "application/json"}
                    )
                    text_out = res.text
                
                info = json.loads(text_out.strip())
                if info.get("isVersionMismatch"):
                    ai_similarity_val = info.get("semanticSimilarity", 0.0) * 0.4 # heavy penalty
                else:
                    ai_similarity_val = info.get("semanticSimilarity", 0.0)
            except Exception as e:
                print(f"Gemini math evaluation bypassed: {e}")
                
        # Priority B: Sentence-Transformers evaluation (local deep embedding model)
        elif self.model:
            try:
                embeddings = self.model.encode([clean_q, clean_t], convert_to_tensor=True)
                cos_sim = util.cos_sim(embeddings[0], embeddings[1])
                ai_similarity_val = float(cos_sim.item())
                ai_similarity_val = max(0.0, min(1.0, ai_similarity_val))
            except Exception as e:
                print(f"SentenceTransformers evaluation bypassed: {e}")
                
        # Final Score: 70% fuzzy metric + 30% deep semantic metric
        final_score = 0.7 * fuzzy_score_val + 0.3 * ai_similarity_val
        
        # Heuristic boost: exact title & primary artist shared (handles features elegantly)
        q_artists_list = [s.strip().lower() for s in re.split(r"[,&]|\bfeat\.?\b|\band\b", artist1, flags=re.IGNORECASE) if s.strip()]
        q_primary_artist = q_artists_list[0] if q_artists_list else ""

        c_artists_list = [s.strip().lower() for s in re.split(r"[,&]|\bfeat\.?\b|\band\b", artist2, flags=re.IGNORECASE) if s.strip()]
        c_primary_artist = c_artists_list[0] if c_artists_list else ""

        clean_q_title = self.clean_text(song1).lower()
        clean_c_title = self.clean_text(song2).lower()

        if clean_q_title == clean_c_title and len(clean_q_title) > 0:
            has_primary_artist_match = q_primary_artist and c_primary_artist and (
                q_primary_artist == c_primary_artist or
                q_primary_artist in c_artists_list or
                c_primary_artist in q_artists_list
            )
            if has_primary_artist_match:
                final_score = max(final_score, 0.95)
        
        # Apply version check mismatch fallbacks
        if self.check_version_mismatch(f"{song1} {artist1}", f"{song2} {artist2}"):
            final_score = final_score * 0.5
            
        return round(final_score, 3)

    def classify_match(self, score):
        if score >= 0.85:
            return "Exact", "🟩 Exact Match"
        elif score >= 0.60:
            return "Similar", "🟨 Similar Match"
        else:
            return "Not Found", "🟥 Not Found"
            
    def find_best_match(self, query_song, query_artist, candidates):
        if not candidates:
            return None, 0.0, "Not Found"
            
        best_candidate = None
        best_score = -1.0
        
        for candidate in candidates:
            c_song = candidate.get("title", "")
            c_artist = candidate.get("artist", "")
            
            score = self.compute_score(query_song, query_artist, c_song, c_artist)
            if score > best_score:
                best_score = score
                best_candidate = candidate
                
        status = self.classify_match(best_score)[0]
        if status == "Not Found" or best_score < 0.60:
            return None, best_score, "Not Found"
            
        return best_candidate, best_score, status
