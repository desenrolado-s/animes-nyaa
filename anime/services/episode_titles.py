"""Episode titles from Jikan, cached locally and indexed by episode number."""
import json
import random
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = 'https://api.jikan.moe/v4/anime/{mal_id}/episodes'
CACHE_TTL = 24 * 60 * 60
MAX_RETRIES = 3


def _cache_path(mal_id):
    return Path.home() / '.cache' / 'anime-nyaa' / 'episode-titles' / f'{mal_id}.json'


def _read_cache(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        titles = value.get('titles')
        if isinstance(titles, dict):
            return value, titles
    except (OSError, ValueError, AttributeError):
        pass
    return None, {}


def _episode_title(item):
    for key in ('title', 'title_romanji', 'title_romaji', 'title_japanese'):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _fetch_page(url):
    """Fetch one Jikan page, retrying rate limits and transient server errors."""
    for attempt in range(MAX_RETRIES):
        request = Request(url, headers={
            'User-Agent': 'AnimeNyaa/1.0 (episode title lookup)',
            'Accept': 'application/json',
        })
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read(2_000_000).decode('utf-8'))
        except HTTPError as error:
            if error.code != 429 and not 500 <= error.code < 600:
                raise
            retry_after = error.headers.get('Retry-After')
        except (TimeoutError, URLError):
            retry_after = None
        if attempt == MAX_RETRIES - 1:
            raise RuntimeError('Jikan indisponível após novas tentativas.')
        try:
            delay = min(float(retry_after), 8.0) if retry_after else 1.5 * (attempt + 1)
        except (TypeError, ValueError):
            delay = 1.5 * (attempt + 1)
        time.sleep(delay + random.uniform(0, 0.25))


def get_episode_titles(mal_id):
    """Return {episode_number: title}; fall back to stale cache on API failure."""
    if not mal_id:
        return {}
    path = _cache_path(mal_id)
    cached, cached_titles = _read_cache(path)
    now = time.time()
    try:
        cache_is_fresh = cached and now - float(cached.get('fetched_at', 0)) < CACHE_TTL
    except (TypeError, ValueError):
        cache_is_fresh = False
    if cache_is_fresh:
        return {int(number): title for number, title in cached_titles.items() if title}

    titles = {}
    page = 1
    try:
        while True:
            url = API_URL.format(mal_id=int(mal_id)) + '?' + urlencode({'page': page})
            result = _fetch_page(url)
            for episode in result.get('data') or []:
                number = episode.get('mal_id')
                # Jikan episode records use mal_id as the episode's ordinal number.
                if isinstance(number, int):
                    title = _episode_title(episode)
                    if title:
                        titles[number] = title
            if not (result.get('pagination') or {}).get('has_next_page'):
                break
            page += 1
            time.sleep(0.36)
        if titles:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps({
                'fetched_at': now,
                'titles': {str(number): title for number, title in titles.items()},
            }, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)
        return titles
    except Exception:
        fallback = titles or cached_titles
        return {int(number): title for number, title in fallback.items() if title}
