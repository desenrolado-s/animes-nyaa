"""Episodes successfully submitted to Last.fm, separate from watch progress."""
import json
import threading
from pathlib import Path


_lock = threading.Lock()
_in_flight = set()


def progress_path():
    return Path.home() / '.local' / 'share' / 'anime-nyaa' / 'lastfm-progress.json'


def _load():
    try:
        value = json.loads(progress_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _key(anilist_id, episode_number):
    if anilist_id is None or not isinstance(episode_number, int) or episode_number < 1:
        return None
    return (str(anilist_id), episode_number)


def claim(anilist_id, episode_number):
    """Claim a pending episode once per process; failures remain retryable."""
    key = _key(anilist_id, episode_number)
    if key is None:
        return False
    with _lock:
        submitted = _load().get(key[0], [])
        if key[1] in submitted or key in _in_flight:
            return False
        _in_flight.add(key)
        return True


def mark_submitted(anilist_id, episode_number):
    key = _key(anilist_id, episode_number)
    if key is None:
        return
    with _lock:
        progress = _load()
        episodes = set(progress.get(key[0], []))
        episodes.add(key[1])
        progress[key[0]] = sorted(episodes)
        path = progress_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
        _in_flight.discard(key)


def release(anilist_id, episode_number):
    key = _key(anilist_id, episode_number)
    if key is None:
        return
    with _lock:
        _in_flight.discard(key)
