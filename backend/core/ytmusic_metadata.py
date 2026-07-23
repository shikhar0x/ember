import sys
import re
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from ytmusicapi import YTMusic

def extract_ids(url: str):
    video_match = re.search(r'[?&]v=([a-zA-Z0-9_-]{11})', url)
    list_match = re.search(r'[?&]list=([a-zA-Z0-9_-]+)', url)
    album_match = re.search(r'(MPREb_[a-zA-Z0-9_-]+)', url)
    return (
        video_match.group(1) if video_match else None,
        list_match.group(1) if list_match else None,
        album_match.group(1) if album_match else None
    )

def get_best_thumbnail(thumbnails, size=544):
    if not thumbnails:
        return None
    url = sorted(thumbnails, key=lambda t: t.get('width', 0), reverse=True)[0]['url']
    if 'googleusercontent.com' in url:
        if '=w' in url:
            url = re.sub(r'=w\d+-h\d+.*', f'=w{size}-h{size}-l90-rj', url)
            return url.split('=')[0] + f'=w{size}-h{size}-l90-rj'
        elif '=s' in url:
            url = re.sub(r'=s\d+.*', f'=s{size}', url)
            return url.split('=')[0] + f'=s{size}'
    return url

def fetch_album_art_worker(args):
    album_id, art_size = args
    try:
        yt = YTMusic()
        album_details = yt.get_album(browseId=album_id)
        url = get_best_thumbnail(album_details.get("thumbnails", []), size=art_size)
        year = album_details.get("year")
        return album_id, {"url": url, "year": year}
    except Exception:
        return album_id, None

def build_album_art_cache(album_ids, art_size=544, workers=6):
    """Fetch cover art and year for a set of album IDs concurrently. Always from get_album()."""
    cache = {}
    album_ids = [a for a in set(album_ids) if a and a.startswith("MPREb_")]
    if not album_ids:
        return cache
    
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_album_art_worker, (aid, art_size)): aid for aid in album_ids}
        for f in as_completed(futures):
            aid, data = f.result()
            if data:
                cache[aid] = data
    return cache

def find_album_via_search(yt, title, artists, video_id):
    try:
        query = f"{title} {artists[0]['name'] if artists else ''}"
        results = yt.search(query, filter="songs", limit=10)
        for r in results:
            if r.get("videoId") == video_id and r.get("album"):
                return r["album"], "search_fallback_exact"
        artist_names = {a["name"].lower() for a in artists}
        for r in results:
            if r.get("title", "").lower() == title.lower():
                r_artists = {a["name"].lower() for a in r.get("artists", [])}
                if artist_names & r_artists and r.get("album"):
                    return r["album"], "search_fallback"
        for r in results:
            if r.get("album"):
                return r["album"], "search_fallback"
    except Exception:
        pass
    return None, None

def process_track(track, video_id=None, art_size=544, album_art_cache={}, album_context=None):
    video_id = video_id or track.get("videoId")
    title = track.get("title")
    
    artists_list = []
    for a in track.get("artists", []):
        if isinstance(a, str):
            artists_list.append({"name": a, "id": None, "url": None})
        else:
            artists_list.append({
                "name": a.get("name"),
                "id": a.get("id"),
                "url": f"https://music.youtube.com/channel/{a.get('id')}" if a.get("id") else None
            })

    album_data = track.get("album", {}) or {}
    if isinstance(album_data, str):
        album_data = {"name": album_data}
    if album_context and (not album_data.get("id") and not album_data.get("name")):
        album_data = album_context
    if album_context:
        merged = dict(album_context)
        merged.update(album_data)
        album_data = merged
    
    album_id = album_data.get("id") if isinstance(album_data, dict) else None
    album_name = album_data.get("name") if isinstance(album_data, dict) else str(album_data)
    album_source = "album" if album_context else ("playlist" if album_id else None)

    cache_data = album_art_cache.get(album_id) if album_id else None
    cover_art_url = cache_data.get("url") if isinstance(cache_data, dict) else (cache_data if isinstance(cache_data, str) else None)
    year = cache_data.get("year") if isinstance(cache_data, dict) else None
    
    if album_context and album_context.get("year") and not year:
        year = album_context.get("year")

    video_thumbnail_url = get_best_thumbnail(track.get("thumbnails", track.get("thumbnail", [])), size=art_size)
    if not video_thumbnail_url and video_id:
        video_thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"

    duration_seconds = track.get("duration_seconds")
    if duration_seconds is None and "length" in track:
        parts = str(track["length"]).split(":")
        try:
            if len(parts) == 2:
                duration_seconds = int(parts[0])*60 + int(parts[1])
            elif len(parts) == 3:
                duration_seconds = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
        except: pass

    return {
        "videoId": video_id,
        "title": title,
        "url": f"https://music.youtube.com/watch?v={video_id}" if video_id else None,
        "artists": artists_list,
        "duration_seconds": duration_seconds,
        "duration_formatted": f"{duration_seconds//60}:{duration_seconds%60:02d}" if duration_seconds else track.get("length"),
        "album": {
            "name": album_name,
            "id": album_id,
            "url": f"https://music.youtube.com/browse/{album_id}" if album_id else None,
            "source": album_source
        },
        "year": year,
        "cover_art_url": cover_art_url,
        "video_thumbnail_url": video_thumbnail_url,
    }

def main():
    parser = argparse.ArgumentParser(description='Get YouTube Music track/playlist/album metadata')
    parser.add_argument('url', help='YouTube Music video, playlist, or album URL / ID')
    parser.add_argument('-o', '--output', help='Write JSON output to file')
    parser.add_argument('--art-size', type=int, default=544, help='Album art size, default 544')
    parser.add_argument('--limit', type=int, default=0, help='Max tracks (0 = all)')
    parser.add_argument('--resolve-albums', action='store_true', help='For tracks with no album, search YTMusic to find one (slower, single-threaded)')
    parser.add_argument('--workers', type=int, default=6, help='Concurrent album art fetch workers, default 6')
    args = parser.parse_args()

    video_id, playlist_id, album_id = extract_ids(args.url)
    if not video_id and not playlist_id and not album_id:
        if re.match(r'^[a-zA-Z0-9_-]{11}$', args.url):
            video_id = args.url
        elif args.url.startswith("MPREb_"):
            album_id = args.url

    if not video_id and not playlist_id and not album_id:
        print(f"Error: Could not parse a Video/Playlist/Album ID from: {args.url}", file=sys.stderr)
        sys.exit(1)

    yt = YTMusic()

    try:
        if album_id and not playlist_id:
            print(f"Fetching album {album_id} ...", file=sys.stderr)
            album = yt.get_album(browseId=album_id)
            album_art_url = get_best_thumbnail(album.get("thumbnails", []), size=args.art_size)
            album_art_cache = {album_id: {"url": album_art_url, "year": album.get("year")}}
            
            album_context = {
                "name": album.get("title"),
                "id": album_id,
                "thumbnails": album.get("thumbnails", []),
                "year": album.get("year")
            }
            tracks = album.get("tracks", [])
            if args.limit > 0:
                tracks = tracks[:args.limit]
            
            results = [process_track(t, art_size=args.art_size, album_art_cache=album_art_cache, album_context=album_context) for t in tracks]

            output = {
                "type": "album",
                "albumId": album_id,
                "title": album.get("title"),
                "artists": album.get("artists"),
                "year": album.get("year"),
                "url": f"https://music.youtube.com/browse/{album_id}",
                "cover_art_url": album_art_url,
                "track_count": len(results),
                "tracks": results
            }
            print(f"\n--- ALBUM: {album.get('title')} – {len(results)} tracks ---", file=sys.stderr)

        elif playlist_id:
            print(f"Fetching playlist {playlist_id} ...", file=sys.stderr)
            limit = args.limit if args.limit > 0 else 100
            pl = yt.get_playlist(playlist_id, limit=limit)
            tracks = pl.get("tracks", [])
            print(f"Playlist: {pl.get('title')} – {len(tracks)} tracks", file=sys.stderr)
            
            playlist_thumbnails = pl.get("thumbnails", [])
            playlist_cover_url = get_best_thumbnail(playlist_thumbnails, size=args.art_size)

            if args.resolve_albums:
                for t in tracks:
                    if not t.get("album"):
                        title = t.get("title")
                        artists = [{"name": a["name"]} for a in t.get("artists", [])]
                        alb, _ = find_album_via_search(yt, title, artists, t.get("videoId"))
                        if alb:
                            t["album"] = alb

            album_ids = [ (t.get("album") or {}).get("id") if isinstance(t.get("album"), dict) else None for t in tracks ]
            print(f"Fetching cover art for {len(set([a for a in album_ids if a]))} unique albums with {args.workers} workers...", file=sys.stderr)
            album_art_cache = build_album_art_cache(album_ids, art_size=args.art_size, workers=args.workers)

            results = [process_track(t, art_size=args.art_size, album_art_cache=album_art_cache) for t in tracks]

            output = {
                "type": "playlist",
                "playlistId": playlist_id,
                "title": pl.get("title"),
                "description": pl.get("description"),
                "author": pl.get("author"),
                "year": pl.get("year"),
                "url": f"https://music.youtube.com/playlist?list={playlist_id}",
                "playlist_cover_url": playlist_cover_url,
                "playlist_thumbnails": playlist_thumbnails,
                "track_count": len(results),
                "tracks": results
            }

        else:
            print(f"Analyzing Track ID: {video_id}...", file=sys.stderr)
            song = yt.get_song(videoId=video_id)
            video_details = song.get("videoDetails", {})
            watch = yt.get_watch_playlist(videoId=video_id)
            track = watch.get("tracks", [{}])[0] if watch.get("tracks") else {}
            if "thumbnail" not in track and video_details.get("thumbnail"):
                track["thumbnail"] = video_details["thumbnail"].get("thumbnails", [])
            track["title"] = track.get("title") or video_details.get("title")
            track["videoId"] = video_id
            if "lengthSeconds" in video_details:
                track["duration_seconds"] = int(video_details["lengthSeconds"])
            if not track.get("artists") and video_details.get("author"):
                track["artists"] = [{"name": n.strip(), "id": None} for n in video_details.get("author", "").replace(" - Topic", "").split(" • ") if n.strip()]
            
            album_data = track.get("album")
            if not album_data:
                artists_list = [{"name": a["name"]} for a in track.get("artists", [])]
                alb, src = find_album_via_search(yt, track["title"], artists_list, video_id)
                if alb:
                    track["album"] = alb

            album_id = (track.get("album") or {}).get("id") if isinstance(track.get("album"), dict) else None
            album_art_cache = build_album_art_cache([album_id], art_size=args.art_size, workers=1) if album_id else {}
            
            result = process_track(track, video_id, art_size=args.art_size, album_art_cache=album_art_cache)
            output = result
            print(f"\n{result['title']} – {', '.join([a['name'] for a in result['artists']])}", file=sys.stderr)
            if result["album"]["name"]:
                print(f"Album: {result['album']['name']}\n{result['album']['url']}", file=sys.stderr)
            print(f"Art: {result['cover_art_url']}", file=sys.stderr)

        output_json = json.dumps(output, indent=2, ensure_ascii=False)
        print(output_json)

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_json)
            print(f"\nSaved to {args.output}", file=sys.stderr)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
