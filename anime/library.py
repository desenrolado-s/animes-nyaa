"""Persistent personal anime list and per-anime favorite batches."""
import json
from pathlib import Path


def library_path():
    return Path.home() / '.local' / 'share' / 'anime-nyaa' / 'library.json'


def load():
    try:
        value = json.loads(library_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'anime': [], 'favorite_batches': {}}
    if not isinstance(value, dict):
        return {'anime': [], 'favorite_batches': {}}
    anime = value.get('anime')
    batches = value.get('favorite_batches')
    return {
        'anime': anime if isinstance(anime, list) else [],
        'favorite_batches': batches if isinstance(batches, dict) else {},
    }


def save(value):
    path = library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def anime_id(media):
    value = (media or {}).get('id')
    return str(value) if value is not None else ''


def contains_anime(media):
    media_id = anime_id(media)
    return bool(media_id and any(anime_id(item) == media_id for item in load()['anime']))


def toggle_anime(media):
    data = load()
    media_id = anime_id(media)
    if not media_id:
        return False
    current = next((item for item in data['anime'] if anime_id(item) == media_id), None)
    if current:
        data['anime'] = [item for item in data['anime'] if anime_id(item) != media_id]
        save(data)
        return False
    saved = dict(media)
    saved['display_title'] = media.get('display_title') or (media.get('title') or {}).get('english') or (media.get('title') or {}).get('romaji') or (media.get('title') or {}).get('native') or 'Anime sem título'
    data['anime'].insert(0, saved)
    save(data)
    return True


def remove_anime(media):
    media_id = anime_id(media)
    data = load()
    data['anime'] = [item for item in data['anime'] if anime_id(item) != media_id]
    save(data)


def update_anime_metadata(media):
    """Refresh a saved anime record without changing its batch favorites."""
    media_id = anime_id(media)
    if not media_id:
        return
    data = load()
    for index, saved in enumerate(data['anime']):
        if anime_id(saved) == media_id:
            merged = dict(saved)
            merged.update(media)
            data['anime'][index] = merged
            save(data)
            return


def is_favorite_batch(media, item):
    media_id = anime_id(media)
    magnet = (item or {}).get('magnet')
    return bool(media_id and magnet and any(
        batch.get('magnet') == magnet
        for batch in load()['favorite_batches'].get(media_id, [])
        if isinstance(batch, dict)
    ))


def favorite_batches(media):
    media_id = anime_id(media)
    if not media_id:
        return []
    saved = load()['favorite_batches'].get(media_id, [])
    rows = []
    for item in saved:
        if not isinstance(item, dict) or not item.get('magnet'):
            continue
        row = dict(item)
        row.setdefault('title', 'Batch salvo')
        row.setdefault('size', 'Tamanho desconhecido')
        row.setdefault('seeders', '—')
        row.setdefault('leechers', '—')
        row.setdefault('downloads', '—')
        row['is_batch'] = True
        rows.append(row)
    return rows


def toggle_favorite_batch(media, item):
    media_id = anime_id(media)
    magnet = (item or {}).get('magnet')
    if not media_id or not magnet:
        return False
    data = load()
    favorites = data['favorite_batches'].setdefault(media_id, [])
    existing = next((batch for batch in favorites if isinstance(batch, dict) and batch.get('magnet') == magnet), None)
    if existing:
        data['favorite_batches'][media_id] = [batch for batch in favorites
                                              if not isinstance(batch, dict) or batch.get('magnet') != magnet]
        if not data['favorite_batches'][media_id]:
            data['favorite_batches'].pop(media_id, None)
        save(data)
        return False
    saved = dict(item)
    saved['magnet'] = magnet
    saved.setdefault('title', 'Batch sem título')
    favorites.insert(0, saved)
    save(data)
    return True
