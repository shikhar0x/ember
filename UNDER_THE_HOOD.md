# Under the Hood

## Part 1: Authentication & Bypassing (The Bearer Token)
Ember does not use the official, heavily rate-limited public Spotify API. Instead, it interacts directly with Spotify's internal GraphQL endpoints (`api-partner.spotify.com/pathfinder`). To do this, it requires a valid WebPlayer Bearer session token.

**Browser Discovery and Launch (`_fetch_token`)**
Ember locates a Chromium-based browser (Chrome, Brave, Edge) installed on your computer, along with an appropriate chromedriver.
- **On Windows:** It launches the browser visibly using your actual user profile (e.g., `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data`). This inherently relies on the fact that you have already logged into Spotify and your session cookies are stored in that profile.
- **On Linux/macOS:** It also uses a visible browser window with your local user profile to bypass Web Application Firewalls (WAF).

**Chrome DevTools Interception**
Before navigating anywhere, Ember enables performance logging in Chrome. This tells the browser to log all internal Chrome DevTools Protocol (CDP) events, specifically allowing Ember to monitor raw network traffic and WebSocket connections leaving the browser.

**The "Ninja Run"**
Ember commands the browser to navigate to the Spotify Web Player. When the page loads, Spotify's internal JavaScript executes, reads your authenticated session cookies, and constructs API requests containing a freshly minted Bearer token. If you are not logged in, Ember will wait up to 5 minutes for you to log in manually through the spawned browser.

**Harvesting the Token**
While the page is loading, Ember aggressively scans the CDP logs for `Network.webSocketCreated` or `Network.requestWillBeSentExtraInfo` events. The moment it spots the `access_token` query parameter or `Authorization: Bearer ...` header, it snatches it. Additionally, it makes a separate request to `clienttoken.spotify.com` to fetch a short-lived `client-token` to bypass modern Spotify restrictions.

**Profile Scraping**
Once authenticated, Ember uses a script injected into the page to extract your Spotify Display Name and Avatar URL directly from the Web Player's user widget.

**Browser Detachment**
Unlike older versions, Ember no longer forcefully kills the browser after harvesting. It uses a detached process, allowing the user to keep the browser window open or manually close it without interference.

**Caching and Execution**
Ember saves the bearer token, client token, and user profile into a local `tokens.json` file. For the rest of the application's lifecycle, the Python backend uses the standard `requests` library (equipped with these tokens) to hit Spotify's internal endpoints at light speed.

## Part 2: The Data Pipeline
When you paste a link into Ember's UI, the frontend immediately makes a `GET /inspect?url=...` request. The backend uses Server-Sent Events (SSE) to stream data back instantly.

Here is how specific link types are handled:

**1. Playlist Links (`/playlist/`)**
- **Fetching:** The backend hits Pathfinder's `playlistV2` GraphQL query using the stolen token. Because playlists can be huge, it uses a generator (`get_playlist_generator`) to fetch tracks in paginated chunks of 50.
- **Displaying:** Ember immediately yields a `header` event to the frontend containing the Playlist Title and Cover Art. Then, as each chunk of 50 tracks arrives, it instantly streams `track_item` events. Background threads concurrently fetch the ISRC codes for these tracks and stream update events to fill in the ISRC badges dynamically.
- **Downloading:** When you initiate the download, `download_controller.download_playlist` spins up a `ThreadPoolExecutor` to process and download multiple tracks concurrently in the background.

**2. Album Links (`/album/`)**
- **Fetching:** Albums use a slightly different Pathfinder query (`queryAlbum`). Unlike playlists, an album query can return up to 300 tracks in a single, fast request.
- **Displaying:** The backend parses the high-fidelity album cover and streams the `header` event. It then loops through the returned tracks and streams them via `track_item` events. Similar to playlists, ISRC codes are fetched asynchronously in the background.
- **Downloading:** Handled identically to playlists via the concurrent thread pool.

**3. Single Track Links (`/track/`)**
- **Fetching:** The backend uses the Pathfinder `getTrack` query to pull metadata.
- **Displaying:** Because the frontend expects an immediate response for a single track and typically closes the SSE connection right after receiving it, the backend fetches the ISRC synchronously before yielding the final `track` event back to the UI.
- **Downloading:** Handled via `download_controller.download` as a standalone synchronous task.

## Part 3: Matching, Downloading, and Tagging
Because audio cannot be downloaded directly from Spotify, Ember finds the equivalent audio on YouTube.

**1. The Matching Process (`resolver.py` & `matcher.py`)**
- **The ISRC Search:** Ember searches YouTube using the track's ISRC code. Record labels upload official audio to YouTube with the ISRC embedded. If an ISRC match is found, Ember is almost guaranteed to get the pristine, official studio audio.
- **Fallback Query Search:** If ISRC fails, it searches YouTube using a specific query: `"{Artist}" "{Title}" official audio`.
- **Blacklist Filtering:** It strips out videos containing negative keywords like "live", "cover", "slowed", "reverb", "8d", "nightcore".
- **Fuzzy Scoring:** It grades the remaining candidates:
  - **Title (50%):** String similarity (`rapidfuzz`) between Spotify and YouTube titles.
  - **Artist (30%):** Checks if the Spotify artist name exists in the YouTube video title or channel name.
  - **Duration (20%):** Applies an exponential decay penalty if the YouTube video length differs from the Spotify track.
  - **The Topic Bonus:** Channels ending in "- Topic" (YouTube Music official auto-generated audio) receive a massive +20% score boost. The candidate with the highest score wins.

**2. The Downloading Process (`yt-dlp`)**
The winning YouTube Video ID is passed to `yt-dlp`, which connects to YouTube's CDN and requests the `bestaudio` stream (usually OPUS or M4A). During the download, `yt-dlp` hooks trigger callbacks that emit byte-level progress events back to the frontend, powering the progress bars. If transcoding is required, FFmpeg is invoked in the background.

**3. The Tagging Process (`tagger.py`)**
Once the raw audio file exists on disk, it is passed to the Tagger (`mutagen`):
- **Cover Art:** It downloads the maximum resolution (640x640 or higher) cover art image from the Spotify CDN and embeds the raw JPEG bytes directly into the audio file headers.
- **Standard ID3 Tags:** It writes Title, Artists, Album Name, Release Year, Genre, Track Number, and Total Tracks into the file.
- **ISRC Injection:** It embeds the ISRC code into the file tags.
- **Finalization:** The file is saved and renamed cleanly in your output folder, and a final `DONE` event is sent to the frontend.
