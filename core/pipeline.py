from core.models import Track, Candidate
from core.resolver import fetch_candidates, _search, _get_active_blacklist
from core.matcher import rank_candidates
from core.utils import normalize_title, normalize_artist


MINIMUM_SCORE        = 0.3
CONFIDENCE_THRESHOLD = 0.7


def resolve(track: Track, allow_edits: bool = False) -> list[Candidate]:
    candidates = fetch_candidates(track, allow_edits=allow_edits)

    if not candidates:
        return []

    ranked_all = rank_candidates(track, candidates)
    if not ranked_all:
        return []

    # --- ISRC PRIORITY ---
    isrc_matches = [c for c in ranked_all if c.is_isrc and c.score >= MINIMUM_SCORE]
    if isrc_matches:
        isrc_matches.sort(key=lambda x: x.score, reverse=True)
        others = [c for c in ranked_all if c.video_id != isrc_matches[0].video_id]
        return [isrc_matches[0]] + others

    # --- LOW CONFIDENCE → EXPAND SEARCH ---
    if ranked_all[0].score < CONFIDENCE_THRESHOLD:
        print(f"[Spyde] Low confidence ({ranked_all[0].score:.2f}). Expanding search...")

        blacklist = _get_active_blacklist(track.title)

                            
        if track.isrc:
            fallback_queries = [f"\"{track.isrc}\""]
        else:
            fallback_queries = []

                                            
        fallback_queries += [
            f"{track.title} {track.artists[0] if track.artists else ''}",
            f"{track.title}"
        ]

        seen = {c.video_id for c in candidates}

        for q in fallback_queries:
            results = _search(
                q,
                100,
                blacklist,
                allow_edits=True                             
            )

            for c in results:
                if c.video_id not in seen:
                    candidates.append(c)
                    seen.add(c.video_id)

                                 
        ranked_all = rank_candidates(track, candidates)
        ranked_all.sort(key=lambda c: c.score, reverse=True)

    return [c for c in ranked_all if c.score >= MINIMUM_SCORE]

def best(track: Track) -> Candidate | None:
    ranked = resolve(track)
    return ranked[0] if ranked else None