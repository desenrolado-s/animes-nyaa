"""Expose the bundled Node.js, WebTorrent CLI, MPV, and GTK runtime to the packaged app."""
import os
import sys

bundle = getattr(sys, '_MEIPASS', None)
if bundle:
    icon_data_dir = os.path.join(bundle, 'share')
    bundled_icon_theme = os.path.join(icon_data_dir, 'icons', 'hicolor', 'index.theme')
    if os.path.isfile(bundled_icon_theme):
        if sys.platform == 'win32':
            existing_data_dirs = os.environ.get('XDG_DATA_DIRS', '')
            os.environ['XDG_DATA_DIRS'] = (
                os.pathsep.join((icon_data_dir, existing_data_dirs))
                if existing_data_dirs else icon_data_dir
            )
        else:
            data_dirs = os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share'
            os.environ['XDG_DATA_DIRS'] = os.pathsep.join((icon_data_dir, data_dirs))

    if sys.platform == 'win32':
        schemas_dir = os.path.join(bundle, 'share', 'glib-2.0', 'schemas')
        if os.path.isfile(os.path.join(schemas_dir, 'gschemas.compiled')):
            os.environ.setdefault('GSETTINGS_SCHEMA_DIR', schemas_dir)

        typelib_candidates = (
            os.path.join(bundle, 'gi_typelibs'),
            os.path.join(bundle, 'lib', 'girepository-1.0'),
        )
        typelib_dirs = [path for path in typelib_candidates if os.path.isdir(path)]
        if typelib_dirs:
            existing_typelibs = os.environ.get('GI_TYPELIB_PATH', '')
            os.environ['GI_TYPELIB_PATH'] = os.pathsep.join(
                typelib_dirs + ([existing_typelibs] if existing_typelibs else [])
            )

        pixbuf_loaders_dir = os.path.join(bundle, 'lib', 'gdk-pixbuf-2.0', '2.10.0', 'loaders')
        pixbuf_cache = os.path.join(bundle, 'lib', 'gdk-pixbuf-2.0', '2.10.0', 'loaders.cache')
        if os.path.isdir(pixbuf_loaders_dir):
            os.environ.setdefault('GDK_PIXBUF_MODULEDIR', pixbuf_loaders_dir)
        if os.path.isfile(pixbuf_cache):
            os.environ.setdefault('GDK_PIXBUF_MODULE_FILE', pixbuf_cache)

    bundled_paths = (
        bundle if sys.platform == 'win32' else '',
        os.path.join(bundle, 'node', 'bin'),
        os.path.join(bundle, 'node'),
        os.path.join(bundle, 'webtorrent-cli', 'node_modules', '.bin'),
        os.path.join(bundle, 'mpv'),
    )
    paths = [path for path in bundled_paths if path and os.path.isdir(path)]
    if paths:
        current_path = os.environ.get('PATH', '')
        os.environ['PATH'] = os.pathsep.join(paths + ([current_path] if current_path else []))
