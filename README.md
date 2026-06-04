# Ember - The Premium Music Downloader

Ember is a bleeding-edge desktop application built with Tauri, Svelte, and Python that redefines the music downloading experience. It fuses a hyper-optimized backend pipeline with a stunning "Liquid Glass" frontend aesthetic to deliver an unparalleled user experience.

![Liquid Glass Aesthetic](assets/cover.png)

## Features

- **Liquid Glass Aesthetic**: A deeply immersive, modern UI featuring pure glassmorphism, floating ambient orbs, and buttery smooth physics-based micro-animations.
- **The "Pulse & Sweep" Progress Engine**: A completely overhauled, byte-by-byte smooth progress bar featuring sweeping light beams, pulsating red shadows, and a continuous sine-wave DNA flow animation.
- **Intelligent Pathfinder**: Feed Ember *any* Spotify Track, Album, or Playlist link. It parses the metadata, queries the Spotify API, and enriches it instantly.
- **Flawless Audio Mapping**: Ember's enrichment engine automatically maps Spotify metadata to the exact corresponding high-quality YouTube audio stream using a dual search-and-verify algorithm.
- **Concurrent Batch Processing**: Download massive 100+ track playlists in parallel. The python worker pool manages throttling, chunking, and file writing synchronously while keeping the UI perfectly responsive.
- **Automatic ID3 Tagging**: Downloads and embeds high-resolution cover art, artist tags, album info, and track numbers directly into the `.mp3` or `.m4a` files.
- **Direct YouTube Video Support**: Not just for Spotify. Paste any YouTube video or Shorts link and select from 1080p MP4 or high-bitrate MP3 extraction.

## Architecture

Ember leverages a two-tier architecture:
1. **Frontend (Tauri + Svelte)**: A highly optimized, reactive user interface with custom CSS animations and a zero-dependency design system.
2. **Backend (Python)**: A robust sidecar executable running a FastAPI-based local API, utilizing `yt-dlp` for raw extraction, `mutagen` for ID3 tagging, and `playwright`/`selenium` driven GraphQL scraping for metadata enrichment.

## Virtual Environment Setup (Required)

Before building from source or running the development server, you **must** set up a Python virtual environment. Ember's development mode explicitly looks for a `.venv` folder to spawn the backend.

```bash
# 1. Create the virtual environment
python -m venv .venv

# 2. Activate it
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

## Building from Source

To compile the application into a standalone installer, ensure your virtual environment is **active**.

### Windows
1. **Build the Python Backend** (Requires PyInstaller):
   ```bash
   pyinstaller ember-backend.spec
   ```
   This creates a standalone sidecar executable `ember-backend.exe` in the `dist/` directory.

2. **Build the Tauri Frontend**:
   ```bash
   cd tauri-app
   npm install
   npm run tauri build
   ```
   Tauri will automatically bundle the backend executable and generate both a standalone `.exe` and an `.msi` installer for you.

### Linux & macOS (Untested)
1. **Build the Python Backend** (Requires PyInstaller):
   ```bash
   pyinstaller ember-backend.spec
   ```
   This creates a standalone binary `ember-backend` (without an extension) in the `dist/` directory.

2. **Update Tauri Config**:
   Open `tauri-app/src-tauri/tauri.conf.json` and change the `resources` array to point to the extensionless binary:
   ```json
   "resources": [
     "../../dist/ember-backend"
   ]
   ```

3. **Build the Tauri Frontend**:
   ```bash
   cd tauri-app
   npm install
   npm run tauri build
   ```
   Tauri will bundle the backend and generate an `.AppImage` and `.deb` package on Linux, or an `.app` and `.dmg` on macOS.

## Development

To run the app in development mode with hot-reloading:

```bash
cd tauri-app
npm run tauri dev
```

---
*Ember. Yours, forever.*
