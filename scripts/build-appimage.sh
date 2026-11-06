#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

appimage_version=${APPIMAGE_VERSION:?Set APPIMAGE_VERSION to the release version}
update_info=${APPIMAGE_UPDATE_INFO:?Set APPIMAGE_UPDATE_INFO to the release zsync URL}
appimage_arch=${APPIMAGE_ARCH:-x86_64}
appdir=build/anime-nyaa.AppDir
appimage="anime-nyaa-linux-${appimage_arch}-v${appimage_version}.AppImage"

test -x dist/anime-nyaa/anime-nyaa
rm -rf "$appdir"
rm -f "dist/$appimage" "${appimage}.zsync" "dist/${appimage}.zsync"
mkdir -p "$appdir/usr/anime-nyaa"
cp -a dist/anime-nyaa/. "$appdir/usr/anime-nyaa/"
mkdir -p "$appdir/usr/anime-nyaa/_internal/certs"
bash scripts/bundle-ca-certificates.sh "$appdir/usr/anime-nyaa/_internal/certs"
bash scripts/bundle-gtk-typelibs.sh "$appdir/usr/anime-nyaa/_internal/gi_typelibs"

# Keep GLib from the host so PyGObject and GTK use one compatible runtime.
find "$appdir" \( -name 'libglib-2.0.so*' -o -name 'libgobject-2.0.so*' \
  -o -name 'libgio-2.0.so*' -o -name 'libgmodule-2.0.so*' \
  -o -name 'libgirepository-*.so*' \) -delete
# GIO loads the host libmount at runtime. Keep its libmount, libblkid and
# libsystemd dependency chain from one distro instead of mixing Ubuntu and
# the target system's symbol versions.
find "$appdir" \( -name 'libmount.so*' -o -name 'libblkid.so*' \
  -o -name 'libsystemd.so*' \) -delete
rm -rf "$appdir/usr/anime-nyaa/_internal/gio_modules" "$appdir/usr/anime-nyaa/gio_modules"
rm -rf "$appdir/usr/anime-nyaa/_internal/share/glib-2.0/schemas"
sed -e "s|@APPIMAGE_VERSION@|${appimage_version}|" \
  -e "s|@APPIMAGE_ARCH@|${appimage_arch}|" \
  packaging/linux/anime-nyaa.desktop > "$appdir/anime-nyaa.desktop"
cp packaging/linux/anime-nyaa.png "$appdir/"
cp packaging/linux/anime-nyaa.png "$appdir/.DirIcon"
test -s "$appdir/anime-nyaa.png"

cat > "$appdir/AppRun" <<'RUN'
#!/bin/sh
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
APP_DIR="$HERE/usr/anime-nyaa"
export PATH="$APP_DIR/_internal/node/bin:$APP_DIR/_internal/webtorrent-cli/node_modules/.bin:$PATH"
GI_TYPELIB_PATH="$APP_DIR/_internal/gi_typelibs${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
for path in /usr/lib64/girepository-1.0 /usr/lib/girepository-1.0 /usr/lib/x86_64-linux-gnu/girepository-1.0; do
  [ -d "$path" ] && GI_TYPELIB_PATH="$GI_TYPELIB_PATH:$path"
done
export GI_TYPELIB_PATH
exec "$APP_DIR/anime-nyaa" "$@"
RUN
chmod +x "$appdir/AppRun"

curl --fail --location --retry 3 \
  https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
  --output build/appimagetool.AppImage
chmod +x build/appimagetool.AppImage
ARCH="$appimage_arch" APPIMAGE_EXTRACT_AND_RUN=1 build/appimagetool.AppImage \
  -u "$update_info" "$appdir" "dist/$appimage"
test -s "dist/$appimage"
test -s "${appimage}.zsync"
mv "${appimage}.zsync" "dist/${appimage}.zsync"
