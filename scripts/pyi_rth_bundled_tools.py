"""Expose the bundled Node.js and WebTorrent CLI to the packaged app."""
import os
import sys

bundle = getattr(sys, '_MEIPASS', None)
if bundle:
    bundled_paths = (
        os.path.join(bundle, 'node', 'bin'),
        os.path.join(bundle, 'webtorrent-cli', 'node_modules', '.bin'),
    )
    paths = [path for path in bundled_paths if os.path.isdir(path)]
    if paths:
        current_path = os.environ.get('PATH', '')
        os.environ['PATH'] = os.pathsep.join(paths + ([current_path] if current_path else []))
