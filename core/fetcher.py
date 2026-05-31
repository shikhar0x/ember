import os
import requests
import yt_dlp
import imageio_ffmpeg


                                                                
_CODEC_EXT = {
    "mp3": "mp3",
    "flac": "flac",
    "m4a": "m4a",
    "aac": "m4a",
    "vorbis": "ogg",
    "opus": "opus",
    "wav": "wav",
}


def fetch_audio(video_id: str, output_dir: str = "downloads", progress_hook=None,
                audio_codec: str = "mp3", audio_quality: str = "320") -> dict:
    os.makedirs(output_dir, exist_ok=True)

    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
    
                                                   
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"]
            }
        },
    
        "noplaylist": True,
        "ignoreerrors": False,
    
        "addmetadata": False,
        "embedthumbnail": False,
    
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
    
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_codec,
            "preferredquality": audio_quality,
        }],
    }

    if progress_hook:
        base_opts["progress_hooks"] = [progress_hook]

    url = f"https://www.youtube.com/watch?v={video_id}"

                            
    formats_to_try = [
        "bestaudio/best",
        "bestaudio",
        "best",
        "worst",                                    
    ]

    last_error = None
    info = None

    for fmt in formats_to_try:
        try:
            ydl_opts = base_opts.copy()
            ydl_opts["format"] = fmt

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                raw_path = ydl.prepare_filename(info)

            print(f"[Spyde] Download succeeded using format: {fmt}")
            break

        except Exception as e:
            print(f"[Spyde] Format '{fmt}' failed: {e}")
            last_error = e
            continue

    if not info:
        raise RuntimeError(f"[Spyde] All extraction strategies failed: {last_error}")

                                                                     
    out_ext = _CODEC_EXT.get(audio_codec, audio_codec)
    output_path = os.path.splitext(raw_path)[0] + f".{out_ext}"

    # ---- Thumbnail ----
    thumb_bytes = None
    thumb_url = info.get("thumbnail")

    if thumb_url:
        try:
            r = requests.get(
                thumb_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10
            )
            if r.status_code == 200:
                thumb_bytes = r.content
        except Exception:
            pass

    return {
        "path": os.path.abspath(output_path),
        "thumbnail_bytes": thumb_bytes
    }


def fetch_cover(url: str) -> bytes | None:
    """
    Fetch cover art bytes from any image URL.
    Used to pull Spotify cover as priority over YouTube thumbnail.
    """
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        if r.status_code == 200:
            return r.content
    except Exception:
        pass

    return None