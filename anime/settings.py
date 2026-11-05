"""Persistent application preferences."""
import json
import os
from pathlib import Path


DEFAULT_TEMP_DIRECTORY = Path('/tmp')


def settings_path():
    return Path.home() / '.local' / 'share' / 'anime-nyaa' / 'settings.json'


def temporary_directory():
    """Return the selected temporary download directory, or /tmp by default."""
    try:
        value = json.loads(settings_path().read_text(encoding='utf-8'))
        directory = value.get('temporary_directory') if isinstance(value, dict) else None
        if directory:
            return Path(directory).expanduser()
    except (OSError, ValueError):
        pass
    return DEFAULT_TEMP_DIRECTORY


def set_temporary_directory(directory):
    """Persist a directory path, or clear it to use the /tmp default."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {'temporary_directory': str(Path(directory).expanduser().resolve()) if directory else None}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)
