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
    return set_watched(anilist_id, [episode_number], True)


def set_watched(anilist_id, episode_numbers, watched):
    """Update a group of episodes in one write, preserving other progress."""
    numbers = {number for number in episode_numbers
               if isinstance(number, int) and not isinstance(number, bool) and number > 0}
    if anilist_id is None or not numbers:
        return False
    progress = load()
    raw = progress.get(str(anilist_id), [])
    episodes = {number for number in raw if isinstance(number, int) and number > 0} if isinstance(raw, list) else set()
    if watched:
        episodes.update(numbers)
    else:
        episodes.difference_update(numbers)
    progress[str(anilist_id)] = sorted(episodes)
    _write(progress)
    return True


def _write(progress):
    path = progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
