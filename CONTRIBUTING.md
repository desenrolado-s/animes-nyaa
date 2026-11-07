# Contributing to Anime Nyaa

Thank you for contributing! Here is a simple guide to help you get started.

> [!IMPORTANT]
> **Always use the `dev` branch!**
> - All new branches and Pull Requests must be based on **`dev`**, not `main`.
> - The `main` branch is reserved for automated stable releases.

---

## 1. Setup

1. **Fork** the repository on GitHub (`https://github.com/desenrolado-s/animes-nyaa`).
2. **Clone** your fork:
   ```sh
   git clone https://github.com/<your-username>/animes-nyaa.git
   cd animes-nyaa
   ```
3. **Add upstream remote**:
   ```sh
   git remote add upstream https://github.com/desenrolado-s/animes-nyaa.git
   git fetch upstream
   ```
4. **Switch to `dev` and create your branch**:
   ```sh
   git checkout dev
   git pull upstream dev
   git checkout -b feat/your-feature-name
   ```

---

## 2. Requirements

Install the necessary dependencies for your Linux distribution:

- **Debian / Ubuntu**:
  ```sh
  sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 mpv nodejs npm
  sudo npm install --global webtorrent-cli
  ```
- **Arch Linux**:
  ```sh
  sudo pacman -S python python-gobject gtk4 libadwaita mpv nodejs npm
  sudo npm install --global webtorrent-cli
  ```
- **Fedora**:
  ```sh
  sudo dnf install python3 python3-gobject gtk4 libadwaita mpv nodejs npm
  sudo npm install --global webtorrent-cli
  ```

---

## 3. Run and Test

### Run the app
Test the application directly by running:

```sh
./anime-nyaa
```

### Run tests
Run the unit test suite before opening a Pull Request:

```sh
python3 -m unittest discover -s tests -v
```

---

## 4. Commits and Pull Request

1. **Commit your changes** using clear messages ([Conventional Commits](https://www.conventionalcommits.org/)):
   - `feat: add new feature`
   - `fix: resolve bug in search parser`
   - `perf: improve catalog load time`

2. **Push to your fork**:
   ```sh
   git push origin feat/your-feature-name
   ```

3. **Open a Pull Request**:
   - Ensure the **base branch is `dev`** (`base: dev` $\leftarrow$ `compare: feat/your-feature-name`).
   - Describe what changed and what you tested.
