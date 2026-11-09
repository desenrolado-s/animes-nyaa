#!/usr/bin/env bash
set -euo pipefail

bundle_root=${1:?Usage: bundle-windows-runtime.sh <bundle-internal-directory>}
mingw_prefix=${MINGW_PREFIX:-/ucrt64}

if [[ ! -d "$mingw_prefix/bin" ]]; then
  echo "MSYS2 MinGW prefix not found at $mingw_prefix" >&2
  exit 1
fi

mkdir -p "$bundle_root"

# 1. Bundle mpv executable into _internal so it shares the coherent UCRT64 DLL set.
if [[ -f "$mingw_prefix/bin/mpv.exe" ]]; then
  install -m 755 "$mingw_prefix/bin/mpv.exe" "$bundle_root/mpv.exe"
else
  echo "Missing $mingw_prefix/bin/mpv.exe" >&2
  exit 1
fi

# 2. Bundle GdkPixbuf loaders and cache (including SVG and PNG/JPEG loaders).
pixbuf_subdir="lib/gdk-pixbuf-2.0/2.10.0"
if [[ -d "$mingw_prefix/$pixbuf_subdir/loaders" ]]; then
  mkdir -p "$bundle_root/$pixbuf_subdir/loaders"
  cp -f "$mingw_prefix/$pixbuf_subdir/loaders/"*.dll "$bundle_root/$pixbuf_subdir/loaders/"
  GDK_PIXBUF_MODULEDIR="$mingw_prefix/$pixbuf_subdir/loaders" \
    "$mingw_prefix/bin/gdk-pixbuf-query-loaders.exe" --update-cache || true
  if [[ -f "$mingw_prefix/$pixbuf_subdir/loaders.cache" ]]; then
    cp -f "$mingw_prefix/$pixbuf_subdir/loaders.cache" "$bundle_root/$pixbuf_subdir/loaders.cache"
  fi
fi

# 3. Collect all required UCRT64 DLLs for GTK4, Libadwaita, Librsvg, GdkPixbuf loaders, and mpv.
roots=(
  "$mingw_prefix/bin/libgtk-4-1.dll"
  "$mingw_prefix/bin/libadwaita-1-0.dll"
  "$mingw_prefix/bin/librsvg-2-2.dll"
  "$mingw_prefix/bin/libgdk_pixbuf-2.0-0.dll"
  "$mingw_prefix/bin/mpv.exe"
)
if [[ -d "$bundle_root/$pixbuf_subdir/loaders" ]]; then
  for loader in "$bundle_root/$pixbuf_subdir/loaders/"*.dll; do
    [[ -f "$loader" ]] && roots+=("$loader")
  done
fi

for target in "${roots[@]}"; do
  if [[ -f "$target" && "$target" == *.dll && "$target" == "$mingw_prefix/bin/"* ]]; then
    cp -f "$target" "$bundle_root/"
  fi
  while IFS= read -r dep; do
    if [[ -n "$dep" && -f "$dep" ]]; then
      cp -f "$dep" "$bundle_root/"
    fi
  done < <(
    ldd "$target" 2>/dev/null \
      | awk '/=>/ { print $3 }' \
      | grep -E "^(${mingw_prefix}|/ucrt64|/mingw64)/bin/.*\.dll$" \
      | sort -u
  )
done

# 4. Compile GSettings schemas so GTK4 and Libadwaita have org.gtk.* and org.gnome.desktop.interface.
schema_src="$mingw_prefix/share/glib-2.0/schemas"
schema_dst="$bundle_root/share/glib-2.0/schemas"
if [[ -d "$schema_src" ]]; then
  mkdir -p "$schema_dst"
  cp -f "$schema_src/"*.xml "$schema_dst/" 2>/dev/null || true
  cp -f "$schema_src/"*.override "$schema_dst/" 2>/dev/null || true
  "$mingw_prefix/bin/glib-compile-schemas.exe" "$schema_dst"
  test -s "$schema_dst/gschemas.compiled"
else
  echo "Missing GSettings schemas directory at $schema_src" >&2
  exit 1
fi

echo "Bundled Windows GTK4, Libadwaita, GdkPixbuf, GSettings schemas, and mpv runtime into $bundle_root."
