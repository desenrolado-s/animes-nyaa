"""Persistent local watch history."""
import json
from datetime import datetime, timezone
from pathlib import Path


def history_path():
    return Path.home() / '.local' / 'share' / 'anime-nyaa' / 'history.json'


def load():
    try:
        value = json.loads(history_path().read_text(encoding='utf-8'))
        return value if isinstance(value, list) else []
    except (OSError, ValueError):
        return []


def record(item, anime=None, file_index=None, file_name=None):
    rows = load()
    entry = {
        'title': (anime or {}).get('display_title') or item['title'],
        'release': item.get('release') or item['title'], 'magnet': item['magnet'],
        'size': item.get('size', ''),
        'watched_at': datetime.now(timezone.utc).isoformat(),
    }
    if file_index is not None:
        entry['file_index'] = file_index
    if file_name:
        entry['episode_file'] = file_name
    if anime and anime.get('id'):
        entry['anilist_id'] = anime['id']
    if (anime or {}).get('coverImage'):
        entry['cover_url'] = (anime['coverImage'] or {}).get('medium')
    elif item.get('cover_url'):
        entry['cover_url'] = item['cover_url']
    if not entry.get('anilist_id') and item.get('anilist_id'):
        entry['anilist_id'] = item['anilist_id']
    rows = [row for row in rows if not (
        row.get('magnet') == entry['magnet'] and
        row.get('file_index') == entry.get('file_index')
    )]
    rows.insert(0, entry)
    _write(rows)


def remove(entry):
    rows = load()
    rows = [row for row in rows if not (
        row.get('magnet') == entry.get('magnet') and
        row.get('file_index') == entry.get('file_index') and
        row.get('watched_at') == entry.get('watched_at')
    )]
    _write(rows)


def clear():
    _write([])


def _write(rows):
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(rows[:200], ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
