"""Persistent application preferences."""
import json
import os
from pathlib import Path
import shutil


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


def cleanup_temporary_directory(active_directories=None):
    """Remove residual anime-nyaa-* temporary directories from storage folders."""
    active = {str(Path(p).resolve()) for p in (active_directories or ())}
    target_dirs = {DEFAULT_TEMP_DIRECTORY, temporary_directory()}
    for parent in target_dirs:
        try:
            if not parent.is_dir():
                continue
            for item in parent.glob('anime-nyaa-*'):
                try:
                    if str(item.resolve()) in active:
                        continue
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    elif item.is_file():
                        item.unlink(missing_ok=True)
                except OSError:
                    pass
        except OSError:
            pass


def language():
    """Return the saved interface language, defaulting to English."""
    value = load()
    return value.get('language') if value.get('language') in ('en', 'pt') else 'en'


def set_language(language_code):
    """Persist the interface language."""
    if language_code not in ('en', 'pt'):
        raise ValueError('Unsupported language')
    value = load()
    value['language'] = language_code
    _save(value)


def load():
    try:
        value = json.loads(settings_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def set_temporary_directory(directory):
    """Persist a directory path, or clear it to use the /tmp default."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = load()
    value['temporary_directory'] = str(Path(directory).expanduser().resolve()) if directory else None
    _save(value)


def lastfm_credentials():
    value = load()
    return {
        'api_key': str(value.get('lastfm_api_key') or ''),
        'api_secret': str(value.get('lastfm_api_secret') or ''),
        'session_key': str(value.get('lastfm_session_key') or ''),
        'username': str(value.get('lastfm_username') or ''),
        'pending_token': str(value.get('lastfm_pending_token') or ''),
        'enabled': bool(value.get('lastfm_enabled', True)),
    }


def set_lastfm_credentials(api_key, api_secret, session_key=None, username=None,
                           pending_token=None, enabled=None):
    value = load()
    value['lastfm_api_key'] = str(api_key or '').strip()
    value['lastfm_api_secret'] = str(api_secret or '').strip()
    if session_key is not None:
        value['lastfm_session_key'] = str(session_key)
        value['lastfm_username'] = str(username or '')
    if pending_token is not None:
        value['lastfm_pending_token'] = str(pending_token)
    if enabled is not None:
        value['lastfm_enabled'] = bool(enabled)
    _save(value)


def _save(value):
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
