"""Reconcile local episode marks with MAL's contiguous watched count."""
import json
import hashlib
import threading
from pathlib import Path

from . import anilist, myanimelist
from ..storage import settings, watch_progress

_lock = threading.RLock()
_sync_lock = threading.Lock()


def _pending_path():
    username = settings.mal_credentials()['username']
    account = hashlib.sha256(username.encode('utf-8')).hexdigest()[:20]
    return Path.home() / '.local' / 'share' / 'anime-nyaa' / f'mal-pending-{account}.json'


def _load_pending():
    try:
        value = json.loads(_pending_path().read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_pending(value):
    path = _pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)


def _baseline_path():
    return _pending_path().with_name(_pending_path().name.replace('mal-pending-', 'mal-baseline-'))


def _load_baselines():
    try:
        value = json.loads(_baseline_path().read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_baselines(value):
    path = _baseline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)


def change(anime_id, numbers, watched):
    numbers = {n for n in numbers if isinstance(n, int) and not isinstance(n, bool) and n > 0}
    if anime_id is None or not numbers:
        return False
    with _lock:
        if settings.mal_credentials()['refresh_token']:
            pending = _load_pending()
            changes = pending.setdefault(str(anime_id), {})
            changes.update({str(n): bool(watched) for n in numbers})
            _save_pending(pending)
        return watch_progress.set_watched(anime_id, numbers, watched)


def contiguous(episodes):
    count = 0
    while count + 1 in episodes:
        count += 1
    return count


def sync(media):
    anime_id = media.get('id')
    credentials = settings.mal_credentials()
    if not anime_id or not credentials['refresh_token']:
        return False
    with _sync_lock:
        mal_id = media.get('idMal') or anilist.mal_id(anime_id)
        if not mal_id:
            raise RuntimeError('Este anime não possui um ID MyAnimeList.')
        remote = myanimelist.get_progress(mal_id)
        with _lock:
            current_account = settings.mal_credentials()
            if not current_account['refresh_token'] or current_account['username'] != credentials['username']:
                return False
            changes = dict(_load_pending().get(str(anime_id), {}))
            episodes = watch_progress.watched_episodes(anime_id) | set(range(1, remote + 1))
            previous = _load_baselines().get(str(anime_id))
            if isinstance(previous, int) and remote < previous:
                episodes.difference_update(range(remote + 1, previous + 1))
            for number, watched in changes.items():
                if watched:
                    episodes.add(int(number))
                else:
                    episodes.discard(int(number))
            # Import remote marks without treating them as local edits.
            current = watch_progress.watched_episodes(anime_id)
            if episodes - current:
                watch_progress.set_watched(anime_id, episodes - current, True)
            if current - episodes:
                watch_progress.set_watched(anime_id, current - episodes, False)
            desired = contiguous(episodes)
        if desired != remote:
            myanimelist.set_progress(mal_id, desired)
        with _lock:
            current_account = settings.mal_credentials()
            if not current_account['refresh_token'] or current_account['username'] != credentials['username']:
                return False
            baselines = _load_baselines()
            baselines[str(anime_id)] = desired
            _save_baselines(baselines)
            pending = _load_pending()
            current_changes = pending.get(str(anime_id), {})
            for number, watched in changes.items():
                if current_changes.get(number) == watched:
                    current_changes.pop(number, None)
            if not current_changes:
                pending.pop(str(anime_id), None)
            _save_pending(pending)
        return True
