"""Expose the bundled Node.js and WebTorrent CLI to the packaged app."""
import os
import sys

bundle = getattr(sys, '_MEIPASS', None)
if bundle:
    icon_data_dir = os.path.join(bundle, 'share')
    bundled_icon_theme = os.path.join(icon_data_dir, 'icons', 'hicolor', 'index.theme')
    if os.path.isfile(bundled_icon_theme):
        data_dirs = os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share'
        os.environ['XDG_DATA_DIRS'] = os.pathsep.join((icon_data_dir, data_dirs))

    bundled_paths = (
        os.path.join(bundle, 'node', 'bin'),
        os.path.join(bundle, 'webtorrent-cli', 'node_modules', '.bin'),
    )
    paths = [path for path in bundled_paths if os.path.isdir(path)]
    if paths:
        current_path = os.environ.get('PATH', '')
        os.environ['PATH'] = os.pathsep.join(paths + ([current_path] if current_path else []))
