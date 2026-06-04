from pathlib import Path
import re
import yt_dlp
import mutagen
import requests

from core.services.cookie_manager import get_brave_cookie_paths
from core.models import Track, VideoItem, ImagePost
from core.spotify import get_track, get_album, get_playlist

_thumb_cache: dict = {}                      

class InputParser:
    @staticmethod
    def parse(input_str: str) -> list[Track]:
        input_str = input_str.strip()
        if not input_str:
            return []

        try:
            # 1. Local File Check: Attempt to resolve input as a system file path
            path = Path(input_str)
            if path.is_file() and path.exists():
                return InputParser._parse_local_file(path)
        except Exception:
            pass

        # 2. Spotify URL Check: Parse specific Spotify entity routes
        if "spotify" in input_str.lower() and ("track" in input_str or "album" in input_str or "playlist" in input_str):
            return InputParser._parse_spotify(input_str)

        # 3. Universal URL Check: Delegate web media to yt-dlp/Instaloader handlers
        if input_str.startswith("http://") or input_str.startswith("https://"):
            return InputParser._parse_universal_url(input_str)

        # 4. Raw Text Search: Fallback for generic queries
        return InputParser._parse_raw_text(input_str)

    @staticmethod
    def _parse_local_file(path: Path) -> list[Track]:
        title = path.stem
        artists = ["Unknown Artist"]
        album = "Unknown Album"
        duration = 0

        try:
            m = mutagen.File(str(path), easy=True)
            if m:
                if 'title' in m:
                    title = m['title'][0]
                if 'artist' in m:
                    artists = [m['artist'][0]]
                if 'album' in m:
                    album = m['album'][0]
                duration = int(m.info.length)
        except Exception:
            if "-" in title:
                parts = title.split("-", 1)
                artists = [parts[0].strip()]
                title = parts[1].strip()

        return [Track(
            title=title,
            artists=artists,
            album=album,
            duration=duration,
            track_number=None,
            total_tracks=None,
            year=None,
            genre=None,
            cover_url=None,
            spotify_url=None,
            isrc=None,
            source="local"
        )]

    @staticmethod
    def _parse_spotify(url: str) -> list[Track]:
        try:
            if "/track/" in url:
                return [get_track(url)]
            elif "/album/" in url:
                try:
                    return get_album(url)
                except Exception as e:
                    raise Exception(f"Album parsing failed: {e}")
            elif "/playlist/" in url:
                return get_playlist(url)

        except Exception as e:
            err_str = str(e)
            print(f"[InputParser] Spotify Parse Error: {err_str}")

            if "private" in err_str.lower():
                raise Exception(
                    "This playlist is private. Make it public or copy tracks to a new playlist."
                )
            elif "404" in err_str:
                raise Exception(
                    "Spotify resource not found (404). Check the link and try again."
                )
            else:
                raise Exception(f"Failed to fetch Spotify metadata: {err_str}")

        return []


    @staticmethod
    def _export_ghost_cookies():
        """Extracts cookies using Ghost Mode and saves them to a temp file for yt-dlp."""
        import os
        import tempfile
        import http.cookiejar
        import glob
        
        cookie_path = os.path.join(tempfile.gettempdir(), "spyde_ghost_cookies.txt")
        
        try:
            import browser_cookie3
            cj = None
            
            for path in get_brave_cookie_paths():
                if path.exists():
                    try:
                        temp_cj = browser_cookie3.brave(cookie_file=str(path), domain_name='instagram.com')
                        if any(c.name == 'sessionid' for c in temp_cj):
                            cj = temp_cj
                            break
                    except Exception:
                        pass
            
            # Fallback to standard browsers if Brave session is unavailable
            if not cj:
                for get_cookies in [browser_cookie3.firefox, browser_cookie3.chrome, browser_cookie3.edge, browser_cookie3.chromium]:
                    try:
                        temp_cj = get_cookies(domain_name='instagram.com')
                        if any(c.name == 'sessionid' for c in temp_cj):
                            cj = temp_cj
                            break
                    except Exception: continue
            
            # Export cookies to Netscape format for yt-dlp compatibility
            if cj:
                mj = http.cookiejar.MozillaCookieJar(cookie_path)
                for cookie in cj:
                    mj.set_cookie(cookie)
                mj.save(ignore_discard=True, ignore_expires=True)
                return cookie_path
                
        except Exception as e:
            print(f"[InputParser] Cookie export failed: {e}")
            
        return None

    @staticmethod
    def _parse_instagram_story(url: str) -> list[Track]:
        import instaloader as _il
        import re
        import requests
        import browser_cookie3
        import os
        import glob

        m = re.search(r'/stories/([^/]+)/(\d+)', url)
        if not m: return []
        username, story_id = m.group(1), m.group(2)

        L = _il.Instaloader(quiet=True, download_pictures=False,
                            download_videos=False, download_comments=False,
                            save_metadata=False)
        
        try:
            cj = None
            for path in get_brave_cookie_paths():
                if path.exists():
                    try:
                        temp_cj = browser_cookie3.brave(cookie_file=str(path), domain_name='instagram.com')
                        if any(c.name == 'sessionid' for c in temp_cj):
                            cj = temp_cj
                            break
                    except Exception:
                        pass

            if cj:
                L.context._session.cookies.update(cj)
                csrf = next((c.value for c in cj if c.name == 'csrftoken'), None)
                L.context.username = username 
                L.context._session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'X-IG-App-ID': '936619743392459',
                    'X-ASBD-ID': '129477',
                    'X-CSRFToken': csrf if csrf else ""
                })
        except: pass

        try:
            profile = _il.Profile.from_username(L.context, username)
            story_item = None
            for story in L.get_stories(userids=[profile.userid]):
                for item in story.get_items():
                    if str(item.mediaid) == story_id:
                        story_item = item
                        break
                if story_item: break
        except Exception as e:
            print(f"[InputParser] Story fetch failed: {e}")
            return []

        if not story_item: return []

        # --- FIX: ALWAYS use .url for preview (JPG), use .video_url for download ---
        preview_url = story_item.url 
        download_url = story_item.video_url if story_item.is_video else story_item.url
        media_type = "audio_video" if story_item.is_video else "image"

        frames = []
        try:
            r = L.context._session.get(preview_url, timeout=15)
            if r.status_code == 200:
                frames = [r.content]
        except: pass

        if frames:
            cache_key = f"story_{story_id}"
            _thumb_cache[cache_key] = {
                'frames': frames,
                'download_urls': [download_url],                       
                'caption': f"Story by {username}",
                'is_video': story_item.is_video,
            }

        is_video = story_item.is_video
        if is_video:
            return [VideoItem(
                title=f"Story by {username}",
                uploader=username,
                url=download_url,
                source="instagram",
                media_type="video",
            )]
        else:
            return [ImagePost(
                title=f"Story by {username}",
                author=username,
                caption=f"Story by {username}",
                download_urls=[download_url],
                media_types=["photo"],
                source="instagram",
                media_type="image",
            )]

    @staticmethod
    def _parse_universal_url(url: str) -> list[Track]:
        import os
        if "instagram.com/p/" in url:
            return InputParser._parse_instagram(url)
        if "instagram.com/stories/" in url:
            return InputParser._parse_instagram_story(url)

        # --- Twitter/X: Use syndication API FIRST (captures images + videos) ---
        is_twitter = any(d in url for d in ["twitter.com/", "x.com/"])
        if is_twitter:
            result = InputParser._parse_twitter(url)
            if result: return result

        # --- Reddit: Use JSON API FIRST (handles image posts yt-dlp can't) ---
        is_reddit = any(d in url for d in ["reddit.com/", "redd.it/"])
        if is_reddit:
            result = InputParser._parse_reddit_image(url)
            if result: return result

                                                                           
        ghost_cookie_file = InputParser._export_ghost_cookies()

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'cookiefile': ghost_cookie_file if ghost_cookie_file and os.path.exists(ghost_cookie_file) else None,
        }
        
        info = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"[InputParser] yt-dlp failed: {e}")

        if info:
            entries = info.get('entries')
            if entries:
                                                            
                entry = entries[0]
                return [VideoItem(
                    title=entry.get('title') or info.get('title') or 'Unknown',
                    uploader=entry.get('uploader') or 'Unknown',
                    url=entry.get('webpage_url') or url,
                    duration=entry.get('duration') or 0,
                    thumbnail_url=entry.get('thumbnail'),
                    source="web",
                    media_type="video",
                )]
            else:
                return [VideoItem(
                    title=info.get('title') or 'Unknown',
                    uploader=info.get('uploader') or 'Unknown',
                    url=url,
                    duration=info.get('duration') or 0,
                    thumbnail_url=info.get('thumbnail'),
                    source="web",
                    media_type="video",
                )]
        
        return []

    @staticmethod
    def _parse_twitter(url: str) -> list[Track]:
        """Extract ALL media (images + videos) from a tweet via syndication API."""
        print("[Spyde] Trying Twitter syndication API...")
        
                          
        tweet_id = None
        m = re.search(r'/status/(\d+)', url)
        if m: tweet_id = m.group(1)
        if not tweet_id: return []

        try:
            api_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=0"
            r = requests.get(api_url, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }, timeout=10)
            if r.status_code != 200:
                print(f"[Spyde] Syndication API returned {r.status_code}")
                return []

            data = r.json()
            text = data.get("text", "")
            user = data.get("user", {}).get("name", "Unknown")
            screen_name = data.get("user", {}).get("screen_name", "")

                                                  
            preview_urls = []                                                        
            download_urls = []                             
            media_types = []                                 

            for media in data.get("mediaDetails", []):
                mtype = media.get("type", "")
                
                if mtype == "photo":
                    img_url = media.get("media_url_https", "")
                    if img_url:
                        preview_urls.append(img_url + "?format=jpg&name=large")
                        download_urls.append(img_url + "?format=jpg&name=4096x4096")
                        media_types.append("photo")

                elif mtype in ("video", "animated_gif"):
                                                          
                    thumb = media.get("media_url_https", "")
                    if thumb:
                        preview_urls.append(thumb + "?format=jpg&name=large")
                    
                                                     
                    variants = media.get("video_info", {}).get("variants", [])
                    mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
                    if mp4s:
                                                       
                        mp4s.sort(key=lambda v: v.get("bitrate", 0), reverse=True)
                        download_urls.append(mp4s[0]["url"])
                    elif variants:
                        download_urls.append(variants[0].get("url", ""))
                    else:
                        download_urls.append(thumb)
                    media_types.append("video")

            if not preview_urls and not download_urls:
                return []

                                                   
            from concurrent.futures import ThreadPoolExecutor
            frames = [None] * len(preview_urls)
            
            def fetch_frame(args):
                idx, img_url = args
                try:
                    ir = requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                    return idx, ir.content if ir.status_code == 200 else None
                except: return idx, None

            with ThreadPoolExecutor(max_workers=4) as ex:
                for idx, data_bytes in ex.map(fetch_frame, enumerate(preview_urls)):
                    if data_bytes:
                        frames[idx] = data_bytes
            
            frames = [f for f in frames if f]

            if frames:
                _thumb_cache[f"tweet_{tweet_id}"] = {
                    'frames': frames,
                    'download_urls': download_urls,
                    'media_types': media_types,
                    'caption': text,
                }

                                  
            has_photos = "photo" in media_types
            has_videos = "video" in media_types
            if has_photos and has_videos:
                detected_type = "mixed"
            elif has_videos:
                detected_type = "audio_video"
            else:
                detected_type = "image"

            title = f"@{screen_name}" if screen_name else user
            return [Track(
                title=f"Post by {title}",
                artists=[screen_name or user],
                album="Twitter/X",
                duration=0,
                track_number=1, total_tracks=len(download_urls),
                year=None, genre=None,
                cover_url=preview_urls[0] if preview_urls else None,
                spotify_url=url,
                isrc=None, source="direct_url",
                media_type=detected_type
            )]

        except Exception as e:
            print(f"[Spyde] Twitter syndication failed: {e}")

                            
        try:
            r = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1)'
            }, timeout=10)
            if r.status_code == 200:
                og_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', r.text)
                if og_match:
                    return [ImagePost(
                    title="Twitter Post",
                    author="Twitter/X",
                    caption="",
                    download_urls=[og_match.group(1)],
                    media_types=["photo"],
                    source="twitter",
                    media_type="image",
                )]
        except Exception as e:
            print(f"[Spyde] Twitter og:image fallback failed: {e}")

        return []

    @staticmethod
    def _parse_reddit_image(url: str) -> list[Track]:
        """Extract image(s) from a Reddit image post via JSON API."""
        print("[Spyde] Trying Reddit image extraction...")

                                    
        clean_url = url.split("?")[0].rstrip("/")
        if "redd.it/" in clean_url:
                                          
            try:
                r = requests.head(clean_url, allow_redirects=True, timeout=10)
                clean_url = r.url.split("?")[0].rstrip("/")
            except: pass

        json_url = clean_url + ".json"
        try:
            r = requests.get(json_url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; Spyde/1.0)'
            }, timeout=10)
            if r.status_code != 200: return []

            data = r.json()
            post = data[0]["data"]["children"][0]["data"]

            title = post.get("title", "Reddit Post")
            author = post.get("author", "Unknown")
            subreddit = post.get("subreddit_name_prefixed", "Reddit")

            image_urls = []

                                                 
            if post.get("is_gallery") and post.get("media_metadata"):
                for item_id, meta in post["media_metadata"].items():
                    if meta.get("status") == "valid" and meta.get("e") == "Image":
                                                       
                        source = meta.get("s", {})
                        img_url = source.get("u", "") or source.get("gif", "")
                        if img_url:
                                                         
                            img_url = img_url.replace("&amp;", "&")
                            image_urls.append(img_url)

                               
            elif post.get("post_hint") == "image" or any(
                post.get("url", "").endswith(ext) for ext in [".jpg", ".png", ".gif", ".webp"]
            ):
                image_urls = [post["url"]]

                                           
            elif post.get("preview", {}).get("images"):
                for img in post["preview"]["images"]:
                    src = img.get("source", {}).get("url", "")
                    if src:
                        image_urls.append(src.replace("&amp;", "&"))

            if not image_urls: return []

                                              
            frames = []
            for img_url in image_urls:
                try:
                    ir = requests.get(img_url, headers={
                        'User-Agent': 'Mozilla/5.0'
                    }, timeout=10)
                    if ir.status_code == 200:
                        frames.append(ir.content)
                except: pass

            if frames:
                cache_key = f"reddit_{post.get('id', 'post')}"
                _thumb_cache[cache_key] = {
                    'frames': frames,
                    'download_urls': image_urls,
                    'caption': title,
                }

            return [ImagePost(
                title=title,
                author=f"u/{author}",
                caption=title,
                download_urls=image_urls,
                media_types=["photo"] * len(image_urls),
                source="reddit",
                media_type="image",
                cover_url=image_urls[0] if image_urls else None,
            )]

        except Exception as e:
            print(f"[Spyde] Reddit JSON parse failed: {e}")

        return []

    @staticmethod
    def _parse_instagram(url: str) -> list[Track]:
        import instaloader as _il
        from concurrent.futures import ThreadPoolExecutor, as_completed

        sc = re.search(r'/p/([A-Za-z0-9_-]+)', url)
        if not sc:
            return []
        shortcode = sc.group(1)

        L = _il.Instaloader(quiet=True, download_pictures=False,
                            download_videos=False, download_comments=False,
                            save_metadata=False)
                            
        # --- ZERO SETUP MAGIC ---
        try:
            import browser_cookie3
            import os
            import glob
            cj = None
            
            for path in get_brave_cookie_paths():
                if path.exists():
                    try:
                        temp_cj = browser_cookie3.brave(cookie_file=str(path), domain_name='instagram.com')
                        if any(cookie.name == 'sessionid' for cookie in temp_cj):
                            cj = temp_cj
                            print(f"[Spyde] Hijacked session from Brave ({path})!")
                            break
                    except Exception:
                        pass

                                                            
            if not cj:
                for get_cookies in [browser_cookie3.firefox, browser_cookie3.chrome, browser_cookie3.edge, browser_cookie3.chromium]:
                    try:
                        temp_cj = get_cookies(domain_name='instagram.com')
                        if any(cookie.name == 'sessionid' for cookie in temp_cj):
                            cj = temp_cj
                            print(f"[Spyde] Hijacked session from {get_cookies.__name__}!")
                            break
                    except Exception:
                        continue

            if cj:
                L.context._session.cookies.update(cj)
                
                # --- THE 403 KILLER ---
                                                                                                  
                csrf_token = next((cookie.value for cookie in cj if cookie.name == 'csrftoken'), None)
                if csrf_token:
                    L.context._session.headers.update({'X-CSRFToken': csrf_token})
                
                                                                                 
                L.context._session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'X-IG-App-ID': '936619743392459' 
                })
                # ----------------------
            else:
                print("[Spyde] No active Instagram login found in Brave or any other browser.")
                
        except Exception as e:
            print(f"[Spyde] Auto-harvest failed (proceeding anonymously): {e}")
        # -------------------------------------

        post = _il.Post.from_shortcode(L.context, shortcode)

                                                         
        slide_urls = []                                                         
        download_urls = []                                                                        
        slide_types = []                                   

        if post.typename == 'GraphSidecar':
            nodes = list(post.get_sidecar_nodes())
            for node in nodes:
                slide_urls.append(node.display_url)                        
                if node.is_video and hasattr(node, 'video_url') and node.video_url:
                    download_urls.append(node.video_url)
                    slide_types.append("video")
                else:
                    download_urls.append(node.display_url)
                    slide_types.append("photo")
        else:
            slide_urls = [post.url]
            if post.is_video and hasattr(post, 'video_url') and post.video_url:
                download_urls = [post.video_url]
                slide_types = ["video"]
            else:
                download_urls = [post.url]
                slide_types = ["photo"]

                                              
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        frames = [None] * len(slide_urls)

        def fetch(idx_u):
            idx, u = idx_u
            r = requests.get(u, headers=headers, timeout=10)
            return idx, r.content if r.status_code == 200 else None

        with ThreadPoolExecutor(max_workers=6) as ex:
            for idx, data in ex.map(fetch, enumerate(slide_urls)):
                if data:
                    frames[idx] = data

        frames = [f for f in frames if f]

        if frames:
            _thumb_cache[shortcode] = {
                'frames': frames,
                'download_urls': download_urls,
                'media_types': slide_types,
                'caption': post.caption or ''
            }
            print(f"[InputParser] Instagram: {len(frames)} frames cached ({slide_types})")

                                      
        has_photos = "photo" in slide_types
        has_videos = "video" in slide_types
        if has_photos and has_videos:
            detected_type = "mixed"
        elif has_videos:
            detected_type = "audio_video"
        else:
            detected_type = "image"

        return [ImagePost(
            title=f"Post by {post.owner_username}",
            author=post.owner_username,
            caption=post.caption or '',
            download_urls=download_urls,
            media_types=slide_types,
            source="instagram",
            media_type=detected_type,
            cover_url=slide_urls[0] if slide_urls else None,
        )]

    @staticmethod
    def _build_universal_track(info: dict, collection_name: str, track_num: int, original_url: str) -> Track:
        title = info.get('title') or info.get('id') or 'Unknown Title'
        uploader = info.get('uploader') or info.get('creator') or info.get('webpage_url_basename') or 'Unknown Creator'
        duration = info.get('duration') or 0
        
        # --- THE AGGRESSIVE COVER ART HUNTER ---
        thumb = info.get('thumbnail')
        if not thumb and info.get('thumbnails'):
            thumb = info['thumbnails'][-1].get('url')
        if not thumb and info.get('ext') in ['jpg', 'jpeg', 'png', 'webp']:
            thumb = info.get('url')
        if not thumb and info.get('entries') and len(info['entries']) > 0:
            first_slide = info['entries'][0]
            thumb = first_slide.get('thumbnail')
            if not thumb and first_slide.get('thumbnails'):
                thumb = first_slide['thumbnails'][-1].get('url')
            if not thumb and first_slide.get('ext') in ['jpg', 'jpeg', 'png', 'webp']:
                thumb = first_slide.get('url')
        # ----------------------------------------

        if "-" in title and uploader == "Unknown Creator":
            parts = title.split("-", 1)
            uploader = parts[0].strip()
            title = parts[1].strip()

        # --- THE DETECTOR ---
        detected_type = "audio_video"
        ext = info.get('ext', '')
        type_field = info.get('_type', '')

        if ext in ['jpg', 'jpeg', 'png', 'webp']:
            detected_type = "image"
        elif "instagram.com/p/" in original_url:
            detected_type = "image"                                               
        elif duration == 0 and type_field == 'playlist':
            detected_type = "image"

        return Track(
            title=title,
            artists=[uploader] if uploader else [],
            album=collection_name,
            duration=duration,
            track_number=track_num,
            total_tracks=None,
            year=None,
            genre=None,
            cover_url=thumb,
            spotify_url=original_url, 
            isrc=None,
            source="direct_url",
            media_type=detected_type  # <--- Handing the tag to the UI!
        )

    @staticmethod
    def _parse_raw_text(text: str) -> list[Track]:
        artists = ["Unknown Artist"]
        title = text

        if "-" in text:
            parts = text.split("-", 1)
            artists = [parts[0].strip()]
            title = parts[1].strip()

        return [Track(
            title=title,
            artists=artists,
            album="Raw Search",
            duration=0,
            track_number=1,
            total_tracks=1,
            year=None,
            genre=None,
            cover_url=None,
            spotify_url=None,
            isrc=None,
            source="text"
        )]