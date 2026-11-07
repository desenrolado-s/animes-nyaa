# Anime Nyaa

A GTK 4 desktop app to browse anime using AniList, find releases on Nyaa, and stream them via WebTorrent directly into mpv.

<img width="1912" height="1027" alt="image" src="https://github.com/user-attachments/assets/2b2a4c60-21a2-45b9-9f4c-c48b2bcd39a2" />

## Requirements

- Linux with GTK 4, Libadwaita, and PyGObject
- Python 3
- mpv
- Node.js & npm (for WebTorrent CLI)

### Install dependencies

**Debian / Ubuntu:**
```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 mpv nodejs npm
npm install --global webtorrent-cli
```

**Arch Linux:**
```sh
sudo pacman -S python-gobject gtk4 libadwaita mpv nodejs npm
npm install --global webtorrent-cli
```

**Fedora:**
```sh
sudo dnf install python3-gobject gtk4 libadwaita mpv nodejs npm
npm install --global webtorrent-cli
```

## Running

Run directly from source:

```sh
./anime-nyaa
```

Pre-built binaries (AppImage and `.tar.gz`) are available on the [Releases](https://github.com/desenrolado-s/animes-nyaa/releases) page.

## Features

- **AniList Catalog**: Browse trending, popular, and seasonal anime with cover art.
- **Nyaa Search**: Automated episode and batch torrent search.
- **Streaming**: Instant playback in mpv via WebTorrent CLI.
- **Library & History**: Save favorites to "My List" and track watch progress locally.
- **Last.fm Integration**: Optional scrobbling of openings and endings via AnimeThemes.

## Project Structure

- `anime-nyaa`: Launcher script.
- `anime_app.py`: Application entry point.
- `anime/application.py`: Window setup and page routing.
- `anime/ui/`: GTK views (catalog, details, history, settings).
- `anime/services/`: AniList, Nyaa, torrent, and Last.fm integrations.
- `anime/storage/`: Local cache and persistent state (`~/.local/share/anime-nyaa/`).

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) before submitting a Pull Request. **Always use the `dev` branch.**
