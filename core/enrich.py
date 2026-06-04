"""
core/enrich.py — Pure enrichment engine (no UI dependency)

Handles batch track enrichment using c.py's parallel Pathfinder + ISRC pipeline.
Returns (updates, error) tuple — caller (GUI or CLI) applies mutations.
"""

from core.spotify import _tm, _extract_track_id


def enrich_tracks(tracks, session_checker=None):
    """
    Batch-enrich a list of Track objects using parallel Pathfinder + spclient.

    Args:
        tracks: list of Track objects with _spotify_track_id attribute
        session_checker: optional callable returning bool — abort if False

    Returns:
        (updates, error) tuple
        updates: list of (target_track, full_dict) tuples
        error: None on success, or {"error": True, "reason": str} on failure
    """
    from core.spotify_client import get_tracks_parallel

    to_enrich = [
        t for t in tracks
        if not getattr(t, '_enriched', False) and hasattr(t, '_spotify_track_id')
    ]

    if not to_enrich:
        return [], None

    track_ids = [t._spotify_track_id for t in to_enrich]

                          
    workers = min(16, max(4, len(track_ids) // 2))

    try:
        results = get_tracks_parallel(track_ids, _tm, max_workers=workers)
    except Exception as e:
        print(f"[Enrichment Error] Batch fetch failed: {e}")
        return [], {"error": True, "reason": str(e)}

                                               
    result_map = {}
    failed_ids = []

    for tid, full in zip(track_ids, results):
        if not full or full.get("error"):
            failed_ids.append(tid)
        else:
            result_map[full.get("track_id", tid)] = full

                                                                        
    if failed_ids:
        print(f"[Enrichment] Retrying {len(failed_ids)} failed tracks...")
        try:
            retry_results = get_tracks_parallel(failed_ids, _tm, max_workers=min(4, len(failed_ids)))
            for full in retry_results:
                if full and not full.get("error"):
                    result_map[full.get("track_id")] = full
        except Exception as e:
            print(f"[Enrichment Error] Retry failed: {e}")
        except Exception:
            pass

    id_map = {t._spotify_track_id: t for t in to_enrich if hasattr(t, "_spotify_track_id")}
    updates = []

    for tid, full in result_map.items():
        if session_checker and not session_checker():
            break

        try:
            target = id_map.get(tid)
            if not target:
                continue

            updates.append((target, full))
        except Exception as e:
            print(f"[Enrichment Error] {tid}: {e}")

    return updates, None


def apply_enrichment_updates(updates):
    """
    Apply collected updates to Track objects.
    Data only improves — never degrades.

    Args:
        updates: list of (target_track, full_dict) tuples

    Returns:
        list of Track objects that were modified
    """
    modified = []
    for target, full in updates:
        changed = False
        if full.get("cover_url") and full["cover_url"] != target.cover_url:
            target.cover_url = full["cover_url"]
            changed = True
        if full.get("album"):
            if (
                not target.album
                or target.album == getattr(target, "_playlist_name", None)
            ):
                target.album = full["album"]
                changed = True
        if full.get("isrc") and not target.isrc:
            target.isrc = full["isrc"]
            changed = True
        target._enriched = True
        if changed:
            modified.append(target)
    return modified
