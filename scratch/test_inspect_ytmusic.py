import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "backend"))

from ytmusicapi import YTMusic
from core.ytmusic_metadata import extract_ids

# Use a real YouTube Music playlist or album URL
# Let's try a popular album URL: https://music.youtube.com/playlist?list=OLAK5uy_m5c8Rpl7z7eZ0Wb_R2c0N3e4yP-0L2Y1g
url = "https://music.youtube.com/playlist?list=OLAK5uy_m5c8Rpl7z7eZ0Wb_R2c0N3e4yP-0L2Y1g"

video_id, list_id, album_id = extract_ids(url)
print("video_id:", video_id)
print("list_id:", list_id)
print("album_id:", album_id)

yt = YTMusic()
try:
    if album_id and not list_id:
        print("Fetching album...")
        album = yt.get_album(browseId=album_id)
        print("Album title:", album.get("title"))
    elif list_id:
        print("Fetching playlist...")
        pl = yt.get_playlist(list_id, limit=300)
        print("Playlist title:", pl.get("title"))
        print("Tracks count:", len(pl.get("tracks", [])))
except Exception as e:
    print("Error:", e)
