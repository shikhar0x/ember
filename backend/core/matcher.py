import math
from rapidfuzz import fuzz
from core.models import Track, Candidate
from core.utils import normalize_title, normalize_artist


W_TITLE    = 0.5
W_ARTIST   = 0.3
W_DURATION = 0.2

LAMBDA = 0.1

TOPIC_BONUS      =  0.20
DURATION_PENALTY = -0.02
DURATION_SLACK   =  5


def _score_title(track_title: str, cand_title: str) -> float:
    a = normalize_title(track_title)
    b = normalize_title(cand_title)
    return fuzz.token_set_ratio(a, b) / 100.0


def _score_artist(track_artists: list, cand_uploader: str, cand_title: str) -> float:
    if not track_artists:
        return 0.5

    uploader = cand_uploader.lower()
    title    = cand_title.lower()
    main     = normalize_artist(track_artists)

    score = 0.0

                                                                          
    if main and (main in uploader or main in title):
        score = 1.0
    else:
                                  
        matches = sum(1 for a in track_artists if a.lower() in uploader or a.lower() in title)
        if matches > 0:
            score = 0.8 + (0.2 * (matches / len(track_artists)))          

    return min(score, 1.0)


def _score_duration(track_dur: int, cand_dur: int) -> float:
    if track_dur <= 0 or cand_dur <= 0:
        return 0.5
                                                                       
    diff = max(0, abs(track_dur - cand_dur) - 2)
    return math.exp(-LAMBDA * diff)


def _is_topic_channel(uploader: str) -> bool:
    return "- topic" in uploader.lower()


def _adjustments(track: Track, candidate: Candidate) -> float:
    adj = 0.0

    if _is_topic_channel(candidate.uploader):
        adj += TOPIC_BONUS

    if track.duration > 0 and candidate.duration > 0:
        diff = abs(track.duration - candidate.duration)
        if diff > DURATION_SLACK:
            adj += DURATION_PENALTY * (diff - DURATION_SLACK)
            
                                                                      
    bad_keywords = [
        "clean", "cover", "slowed", "reverb",
        "8d", "live", "instrumental", "karaoke",
        "remix", "bass boosted", "bassboosted",
        "sped up", "nightcore",
        "lyrics", "lyric video"
    ]
    cand_t = candidate.title.lower()
    orig_t = track.title.lower()
    
    for word in bad_keywords:
        if word in cand_t and word not in orig_t:
            adj -= 0.15

    return adj


def score_candidate(track: Track, candidate: Candidate) -> float:
    s_title    = _score_title(track.title, candidate.title)
    s_artist   = _score_artist(track.artists, candidate.uploader, candidate.title)
    s_duration = _score_duration(track.duration, candidate.duration)

    base = (
        W_TITLE    * s_title +
        W_ARTIST   * s_artist +
        W_DURATION * s_duration
    )

    adj   = _adjustments(track, candidate)
    final = round(base + adj, 4)

    return final


def rank_candidates(track: Track, candidates: list[Candidate]) -> list[Candidate]:
    for c in candidates:
        c.score = score_candidate(track, c)

    return sorted(candidates, key=lambda c: c.score, reverse=True)