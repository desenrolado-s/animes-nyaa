#!/usr/bin/env bash
set -euo pipefail

destination=${1:?Usage: bundle-gtk-icons.sh DESTINATION_DIRECTORY}
icon_theme=${ADWAITA_ICON_THEME_DIR:-/usr/share/icons/Adwaita}
copyright_file=${ADWAITA_ICON_COPYRIGHT_FILE:-/usr/share/doc/adwaita-icon-theme/copyright}

if [[ ! -d "$icon_theme/symbolic" ]]; then
  echo "Adwaita symbolic icons were not found at $icon_theme." >&2
  exit 1
fi
if [[ ! -s "$copyright_file" ]]; then
  echo "Adwaita icon theme copyright notice was not found at $copyright_file." >&2
  exit 1
fi

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

icon_directory="$destination/hicolor/symbolic/actions"
app_icon_directory="$destination/hicolor/256x256/apps"
license_directory="$(dirname "$(dirname "$destination")")/licenses"
mkdir -p "$icon_directory" "$app_icon_directory" "$license_directory"

mapfile -t icon_names < <(
  grep -REho --include='*.py' "['\"][[:alnum:]-]+-symbolic['\"]" anime \
    | tr -d "'\"" \
    | sort -u
)
if [[ ${#icon_names[@]} -eq 0 ]]; then
  echo 'No symbolic GTK icons were found in the application source.' >&2
  exit 1
fi

for icon_name in "${icon_names[@]}"; do
  source_icon=$(find "$icon_theme/symbolic" -type f -name "$icon_name.svg" -print -quit)
  if [[ -z "$source_icon" ]]; then
    echo "Missing Adwaita symbolic icon: $icon_name" >&2
    exit 1
  fi
  install -m 0644 "$source_icon" "$icon_directory/$icon_name.svg"
done

install -m 0644 packaging/linux/anime-nyaa.png "$app_icon_directory/anime-nyaa.png"
install -m 0644 packaging/linux/anime-nyaa.png \
  "$app_icon_directory/io.github.desenrolado_s.AnimeNyaa.png"

cat > "$destination/hicolor/index.theme" <<'EOF'
[Icon Theme]
Name=Hicolor
Comment=Fallback icons bundled with Anime Nyaa
Hidden=true
Directories=symbolic/actions,256x256/apps

[symbolic/actions]
Size=16
MinSize=8
MaxSize=512
Type=Scalable
Context=Actions

[256x256/apps]
Size=256
Type=Fixed
Context=Applications
EOF

cp "$copyright_file" "$license_directory/adwaita-icon-theme.copyright"
printf 'Bundled %s Adwaita symbolic fallback icons.\n' "${#icon_names[@]}"
