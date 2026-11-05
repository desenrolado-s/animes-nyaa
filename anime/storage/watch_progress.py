"""Persistent episode watch progress, independent from the playback history."""
import json
from pathlib import Path


def progress_path():
    return Path.home() / '.local' / 'share' / 'anime-nyaa' / 'watch-progress.json'


def load():
    try:
        value = json.loads(progress_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def watched_episodes(anilist_id):
    if anilist_id is None:
        return set()
    raw = load().get(str(anilist_id), [])
    if not isinstance(raw, list):
        return set()
    return {number for number in raw if isinstance(number, int) and number > 0}


def mark_watched(anilist_id, episode_number):
    if anilist_id is None or not isinstance(episode_number, int) or episode_number < 1:
        return False
    progress = load()
    episodes = set(watched_episodes(anilist_id))
    episodes.add(episode_number)
    progress[str(anilist_id)] = sorted(episodes)
    _write(progress)
    return True


def _write(progress):
    path = progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
