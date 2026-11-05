# PyInstaller spec for the host GTK/Libadwaita runtime bundle.
a = Analysis(
    ['anime_app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'gi.repository.Gtk',
        'gi.repository.Adw',
        'gi.repository.Gio',
        'gi.repository.GLib',
    ],
    hookspath=[],
    hooksconfig={'gi': {'icons': [], 'themes': [], 'languages': []}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='anime-nyaa',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='anime-nyaa',
)
