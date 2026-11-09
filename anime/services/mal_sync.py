"""Opt-in episode tracking with non-decreasing automatic MAL updates."""
import hashlib
import json
import threading
from pathlib import Path

from . import anilist, myanimelist
from ..storage import settings, watch_progress

_lock = threading.RLock()
_sync_lock = threading.Lock()
_revisions = {}


def revision(anime_id, username):
    with _lock:
        return _revisions.get((username, str(anime_id)), 0)


def reserve_manual_edit(anime_id, username):
    with _lock:
        key = (username, str(anime_id))
        _revisions[key] = _revisions.get(key, 0) + 1
        return _revisions[key]


def _tracking_path(username):
    account = hashlib.sha256(username.encode('utf-8')).hexdigest()[:20]
    return Path.home() / '.local' / 'share' / 'anime-nyaa' / f'mal-tracking-{account}.json'


def _load_tracking(username):
    try:
        value = json.loads(_tracking_path(username).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return set()
    return {str(item) for item in value} if isinstance(value, list) else set()


def is_tracked(anime_id, username=None):
    creds = settings.mal_credentials()
    username = username if username is not None else creds['username']
    if not anime_id or not username:
        return False
    with _lock:
        return str(anime_id) in _load_tracking(username)


def set_tracked(anime_id, tracked):
    creds = settings.mal_credentials()
    if not anime_id or not creds['refresh_token'] or not creds['username']:
        return False
    with _lock:
        reserve_manual_edit(anime_id, creds['username'])
        anime = _load_tracking(creds['username'])
        if tracked:
            anime.add(str(anime_id))
        else:
            anime.discard(str(anime_id))
        path = _tracking_path(creds['username'])
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(sorted(anime), indent=2), encoding='utf-8')
        temp.replace(path)
    return True


def change(anime_id, numbers, watched):
    """Save local changes; unmarking never lowers MAL automatically."""
    with _lock:
        return watch_progress.set_watched(anime_id, numbers, watched)


def contiguous(episodes):
    count = 0
    while count + 1 in episodes:
        count += 1
    return count


def sync(media, push_through=None, expected_revision=None):
    """Import MAL progress; optionally advance, but never lower, the remote count."""
    anime_id = media.get('id')
    credentials = settings.mal_credentials()
    if not credentials['refresh_token'] or not is_tracked(anime_id, credentials['username']):
        return False
    with _sync_lock:
        mal_id = media.get('idMal') or anilist.mal_id(anime_id)
        if not mal_id:
            raise RuntimeError('Este anime não possui um ID MyAnimeList.')
        status = myanimelist.get_list_status(mal_id)
        remote = max(0, int((status or {}).get('num_episodes_watched') or 0))
        with _lock:
            current = settings.mal_credentials()
            if (not current['refresh_token'] or current['username'] != credentials['username'] or
                    not is_tracked(anime_id, credentials['username'])):
                return False
            episodes = watch_progress.watched_episodes(anime_id)
            # Imported MAL history is authoritative; preserve any isolated local marks.
            missing = set(range(1, remote + 1)) - episodes
            if missing:
                watch_progress.set_watched(anime_id, missing, True)
            desired = contiguous(episodes | missing)
        if push_through is not None:
            desired = min(desired, push_through)
        if push_through is not None and desired > remote:
            if (not is_tracked(anime_id, credentials['username']) or
                    (expected_revision is not None and revision(anime_id, credentials['username']) != expected_revision)):
                return False
            # Recheck immediately before writing so a newer remote value is not
            # replaced by a smaller value read at the start of synchronization.
            latest = myanimelist.get_list_status(mal_id) or {}
            if int(latest.get('num_episodes_watched') or 0) >= desired:
                return True
            current = settings.mal_credentials()
            if (not current['refresh_token'] or current['username'] != credentials['username'] or
                    not is_tracked(anime_id, credentials['username']) or
                    (expected_revision is not None and revision(anime_id, credentials['username']) != expected_revision)):
                return False
            myanimelist.set_progress(mal_id, desired)
        return True


def save_manual(anime_id, mal_id, username, changes):
    with _sync_lock:
        credentials = settings.mal_credentials()
        if not credentials['refresh_token'] or credentials['username'] != username or not is_tracked(anime_id, username):
            raise RuntimeError('MyAnimeList account or tracking changed')
        return myanimelist.update_list_status(mal_id, changes)
