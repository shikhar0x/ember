# Release Notes: Ember v1.1.0 🔥

A quality-of-life and polish update that brings a **custom frameless window**, more reliable Spotify sessions, smarter downloads, and several bug fixes.

---

## What's New

### 🪟 Custom Title Bar & Frameless Window
- **Custom Title Bar:** Ember now uses its own sleek title bar with minimize, maximize, and close controls — replacing the default OS chrome for a cleaner, more immersive look.
- **Whole-Window Dragging:** Click and drag anywhere on the window background to reposition it, with smart exclusions for buttons, inputs, and other interactive elements.
- **Resize Borders:** Custom invisible resize handles around the frameless window provide smooth edge and corner resizing on all platforms.

### 🔐 Spotify Session Reliability
- **Token Expiration Fix:** Resolved a bug where expired tokens were not being refreshed correctly, which could leave the app stuck on "Connecting to Spotify…".
- **Windows Browser Fallback:** Improved browser-cookie login logic on Windows to better detect and fall back across Brave, Chrome, and Edge when capturing your Spotify session.

### ⬇️ Download Improvements
- **Per-Track Status Indicators:** During batch/playlist downloads, each track now shows a real-time status — a spinning loader while downloading, a green checkmark on success, or a red cross on failure — replacing the checkbox inline.
- **Silent Retries:** Failed downloads are now automatically retried in the background — no manual intervention needed for transient network hiccups.
- **YouTube Quality Fix (Windows):** Fixed an issue where the selected video resolution was not being applied correctly on Windows.
- **YTMusic Playlist Rate-Limiting:** Large YouTube Music playlists no longer stall or error out due to API throttling; Ember now paces requests appropriately.
- **Unified FFmpeg Logic:** Consolidated duplicate FFmpeg download and setup paths into a single, more robust pipeline shared across Spotify and YouTube downloaders.

### 📂 Open Downloads Folder
- **Quick Access Button:** A new button in the profile menu lets you jump straight to your downloads folder from within the app.
- **No More Auto-Opening:** The downloads folder no longer pops open automatically after every download — access it manually whenever you need it.
- **Cross-Platform Fallback:** Uses the Tauri opener plugin as a fallback to ensure folder opening works reliably on both Windows and Linux.

### 📋 UI & Metadata Polish
- **Profile Menu Reorder:** The "Open Downloads" button now appears above "About" in the profile dropdown for quicker access.
- **Year in YouTube Playlists:** YouTube and YouTube Music playlist items now display their release year alongside existing metadata.
- **Progress Reset on New URL:** Inspecting a new URL now properly resets any previous progress bars, preventing stale or misleading state.
- **Single Toast Fix:** Duplicate toast notifications no longer stack — only one notification is shown per event.
- **Conditional Format Toggle:** The audio format selector now intelligently shows or hides based on the current download context.

---

## Installation & Setup

### Platform Binaries
Please download the appropriate installation asset for your platform from the **Assets** section below:

| Operating System | Installer Type | Package / Executable Name | Description |
| :--- | :--- | :--- | :--- |
| **Windows** | `.msi` Setup | [`Ember_1.1.0_x64_en-US.msi`](https://github.com/shikhar0x/ember/releases/download/v1.1.0/Ember_1.1.0_x64_en-US.msi) | Recommended desktop installer |
| **Windows** | Portable Executable | [`Ember_1.1.0_x64.exe`](https://github.com/shikhar0x/ember/releases/download/v1.1.0/Ember_1.1.0_x64-setup.exe) | Standalone executable version |
| **Linux** | AppImage | [`Ember_1.1.0_amd64.AppImage`](https://github.com/shikhar0x/ember/releases/download/v1.1.0/Ember_1.1.0_amd64.AppImage) | Portable binary format (no install required) |
| **Linux** | Debian/Ubuntu | [`Ember_1.1.0_amd64.deb`](https://github.com/shikhar0x/ember/releases/download/v1.1.0/Ember_1.1.0_amd64.deb) | Standard package for Debian/Ubuntu systems |
| **Linux** | RedHat/Fedora | [`Ember-1.1.0-1.x86_64.rpm`](https://github.com/shikhar0x/ember/releases/download/v1.1.0/Ember-1.1.0-1.x86_64.rpm) | Package for RPM-based systems |

*On first launch in a while, a browser window may open automatically. Click **"Web Player"** so Ember can capture your Spotify session. This only happens once every one hour. It is recommended to have Brave Browser installed in your system.*

---

## Troubleshooting

- **Stuck on "Connecting to Spotify..."**: Make sure you are logged into Spotify in Brave, Chrome, or Edge, then use the **Try Again** button in the app. v1.1.0 significantly improves token handling, so this should be much less frequent.
- **Windows profile lock error**: Ember copies your browser profile to a temp directory rather than using it directly, so you generally don't need to close your browser first (though on Windows you might still sometimes need to close active browser windows if a lock persists).
- **Downloads failing silently**: If a download appears stuck, check your network connection. Ember now retries automatically, but persistent failures will still surface after retries are exhausted.

---

*Thank you for using Ember! Please report any bugs or feature ideas by opening a [GitHub issue](https://github.com/shikhar0x/ember/issues).*

**Full Changelog**: https://github.com/shikhar0x/ember/compare/v1.0.0...v1.1.0
