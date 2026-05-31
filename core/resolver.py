import yt_dlp
from core.models import Candidate
from core.utils import normalize_title, normalize_artist

NEGATIVE_KEYWORDS = [
    "live", "concert", "cover",
    "slowed", "reverb", "8d", "nightcore",
    "karaoke", "bass boosted", "bassboosted",
    "bass boost", "remix", "edit", "version",
    "sped up", "speed up", "lofi",
    "1 hour", "loop", "extended",
    "edit audio", "visualizer"
]

def _build_query(title: str, artists: list) -> str:
    clean_title = normalize_title(title)
    main_artist = normalize_artist(artists)
    return f'"{main_artist}" "{clean_title}" official audio'

def _get_active_blacklist(track_title: str) -> list[str]:
    title_lower = track_title.lower()
    return [kw for kw in NEGATIVE_KEYWORDS if kw not in title_lower]

def _is_bad(title: str, blacklist: list[str], allow_edits: bool) -> bool:
    t = title.lower()

    if allow_edits:
                                     
        if any(x in t for x in ["1 hour", "loop", "extended"]):
            return True
        return False

                 
    if any(kw in t for kw in blacklist):
        return True

    return False

def _search(query: str, max_results: int, blacklist: list[str], is_isrc: bool = False, search_prefix: str = "ytsearch", allow_edits: bool = False) -> list[Candidate]:
    ydl_opts = {
        "quiet":              True,
        "no_warnings":        True,
        "skip_download":      True,
        "extract_flat":       "in_playlist",
        "default_search":     f"{search_prefix}{max_results}",
        "noplaylist":         True,
    }

    candidates = []
    seen       = set()

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            if is_isrc:
                                                           
                results = ydl.extract_info(f"{search_prefix}1:{query}", download=False)
            else:
                results = ydl.extract_info(query, download=False)
        except Exception:
            return []

        if not results or "entries" not in results:
            return []

        for entry in results.get("entries", []):
            if not entry:
                continue

            video_id = entry.get("id")
            title    = entry.get("title", "")
            uploader = entry.get("uploader", "")
            duration = entry.get("duration") or 0

            if not video_id or not title:
                continue
            if video_id in seen:
                continue
            if _is_bad(title, blacklist, allow_edits):
                continue

            seen.add(video_id)
            candidates.append(Candidate(
                video_id = video_id,
                title    = title,
                uploader = uploader,
                duration = int(duration),
                score    = 0.0
            ))

    return candidates

def fetch_candidates(track, max_results: int = 50, allow_edits: bool = False) -> list[Candidate]:
    # --- THE DIRECT URL BYPASS ---
                                                                                 
                                                                                   
    if track.source in ["youtube", "direct_url"] and track.spotify_url:
        return [Candidate(
            video_id = track.spotify_url,                                           
            title    = track.title,
            uploader = track.artists[0] if track.artists else "Unknown",
            duration = track.duration,
            score    = 100.0                                                 
        )]

    blacklist  = _get_active_blacklist(track.title)
    seen       = set()
    candidates = []

    # --- CONTEXT-AWARE SEARCHING ---
                                                                                                      
    prefix = "ytsearch"

    # ---- Primary: ISRC search ----
    if getattr(track, 'isrc', None):
                          
        isrc_results = _search(track.isrc, 3, blacklist, is_isrc=True, search_prefix=prefix, allow_edits=allow_edits)    

                                   
        hybrid_query = f"{track.isrc} {track.title} {track.artists[0] if track.artists else ''}"
        hybrid_results = _search(hybrid_query, 5, blacklist, search_prefix=prefix, allow_edits=allow_edits)  

        for c in isrc_results + hybrid_results:
            if c.video_id not in seen:
                seen.add(c.video_id)
                c.is_isrc = True
                candidates.append(c)

    # ---- Secondary: standard query ----
                                                                              
    query = _build_query(track.title, track.artists) if track.source == "spotify" else track.title
    
    query_results = _search(query, max_results, blacklist, search_prefix=prefix, allow_edits=allow_edits)
    for c in query_results:
        if c.video_id not in seen:
            seen.add(c.video_id)
            candidates.append(c)

    # ---- HARD FILTER (duration verification) ----
    if track.duration > 0:
        verified = [
            c for c in candidates
            if c.duration > 0 and abs(c.duration - track.duration) <= 4
        ]

                                                     
        if verified:
            candidates = verified

    return candidates