#!/usr/bin/env bash
set -euo pipefail

destination=${1:?Usage: bundle-gtk-typelibs.sh DESTINATION_DIRECTORY}
mkdir -p "$destination"

search_dirs=()
IFS=: read -r -a env_dirs <<< "${GI_TYPELIB_PATH:-}"
for directory in "${env_dirs[@]}" "${MINGW_PREFIX:-/ucrt64}/lib/girepository-1.0" /mingw64/lib/girepository-1.0 /usr/lib64/girepository-1.0 /usr/lib/girepository-1.0 /usr/lib/x86_64-linux-gnu/girepository-1.0; do
  [ -n "$directory" ] && [ -d "$directory" ] || continue
  case " ${search_dirs[*]-} " in
    *" $directory "*) ;;
    *) search_dirs+=("$directory") ;;
  esac
done

typelibs=(
  Adw-1 Gtk-4.0 Gdk-4.0 Gsk-4.0 GdkX11-4.0 GdkWayland-4.0 GdkWin32-4.0
  Graphene-1.0 Pango-1.0 PangoCairo-1.0 cairo-1.0
  GdkPixbuf-2.0 GModule-2.0 freetype2-2.0 HarfBuzz-0.0
  GLib-2.0 GObject-2.0 Gio-2.0 GioUnix-2.0 GioWin32-2.0 win32-1.0 xlib-2.0
)
required=(Adw-1 Gtk-4.0 Gdk-4.0 Gsk-4.0 Graphene-1.0)

for name in "${typelibs[@]}"; do
  for directory in "${search_dirs[@]}"; do
    if [ -f "$directory/$name.typelib" ]; then
      cp -f "$directory/$name.typelib" "$destination/"
      break
    fi
  done
done

for name in "${required[@]}"; do
  if [ ! -s "$destination/$name.typelib" ]; then
    echo "Missing required GTK typelib: $name" >&2
    echo "Searched: ${search_dirs[*]}" >&2
    exit 1
  fi
done
