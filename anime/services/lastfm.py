"""Last.fm authentication/scrobbling and AnimeThemes opening/ending lookup."""
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LASTFM_URL = 'https://ws.audioscrobbler.com/2.0/'
AUTH_URL = 'https://www.last.fm/api/auth/'
THEMES_URL = 'https://api.animethemes.moe/anime/'


def _signature(parameters, secret):
    payload = ''.join(f'{key}{parameters[key]}' for key in sorted(parameters)) + secret
    return hashlib.md5(payload.encode('utf-8')).hexdigest()


def _api_call(parameters, api_secret, post=False):
    values = dict(parameters)
    values['api_sig'] = _signature(values, api_secret)
    values['format'] = 'json'
    body = urlencode(values).encode('utf-8')
    request = Request(LASTFM_URL, data=body if post else None,
                      headers={'Content-Type': 'application/x-www-form-urlencoded',
                               'User-Agent': 'AnimeNyaa/1.0'})
    if not post:
        request = Request(LASTFM_URL + '?' + body.decode('ascii'),
                          headers={'User-Agent': 'AnimeNyaa/1.0'})
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read(1_000_000).decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise RuntimeError(f'Não foi possível acessar o Last.fm: {error}') from error
    if 'error' in result:
        raise RuntimeError(result.get('message') or 'O Last.fm recusou a solicitação.')
    return result


def request_token(api_key, api_secret):
    result = _api_call({'method': 'auth.getToken', 'api_key': api_key}, api_secret)
    token = result.get('token')
    if not token:
        raise RuntimeError('O Last.fm não retornou um token de autorização.')
    return token


def authorization_url(api_key, token):
    return AUTH_URL + '?' + urlencode({'api_key': api_key, 'token': token})


def create_session(api_key, api_secret, token):
    result = _api_call({'method': 'auth.getSession', 'api_key': api_key,
                        'token': token}, api_secret)
    session = result.get('session') or {}
    if not session.get('key'):
        raise RuntimeError('O Last.fm não criou uma sessão. Autorize o app e tente novamente.')
    return session['key'], session.get('name', '')


def _cache_path(anilist_id):
    return Path.home() / '.cache' / 'anime-nyaa' / 'themes' / f'{anilist_id}.json'


def _included_index(included):
    return {(item.get('type'), str(item.get('id'))): item
            for item in included if isinstance(item, dict)}


def _related(index, relationships, name, kind=None):
    relation = (relationships or {}).get(name) or {}
    identifiers = relation.get('data') or []
    if isinstance(identifiers, dict):
        identifiers = [identifiers]
    return [index.get((item.get('type'), str(item.get('id'))))
            for item in identifiers if not kind or item.get('type') == kind
            if index.get((item.get('type'), str(item.get('id'))))]


def _fetch_themes(anilist_id):
    query = urlencode({'filter[external_id]': int(anilist_id), 'filter[site]': 'AniList',
                       'filter[has]': 'resources',
                       'include': 'animethemes.song.artists,animethemes.animethemeentries'})
    request = Request(THEMES_URL + '?' + query, headers={
        'Accept': 'application/vnd.api+json', 'User-Agent': 'AnimeNyaa/1.0',
    })
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read(4_000_000).decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise RuntimeError(f'Não foi possível buscar os temas de abertura e encerramento: {error}') from error

    themes = []
    # AnimeThemes follows JSON:API query conventions, but its response uses a
    # custom wrapper and puts attributes/relationships directly on each object.
    # For example: {"anime": [{"animethemes": [{"song": {...}}]}]}.
    anime_items = result.get('anime')
    if isinstance(anime_items, dict):
        anime_items = [anime_items]
    if isinstance(anime_items, list):
        for anime in anime_items:
            for theme in anime.get('animethemes') or []:
                song = theme.get('song') or {}
                title = song.get('title')
                if not title:
                    continue
                artists = []
                for artist in song.get('artists') or []:
                    name = artist.get('name') if isinstance(artist, dict) else artist
                    if name and name not in artists:
                        artists.append(name)
                entries = theme.get('animethemeentries') or []
                ranges = [str(entry.get('episodes') or '').strip()
                          for entry in entries if isinstance(entry, dict)]
                themes.append({'type': str(theme.get('type') or '').upper(),
                               'sequence': theme.get('sequence') or 0,
                               'title': title.strip(), 'artist': ', '.join(artists),
                               'episodes': [value for value in ranges if value]})

    # Tolerate standard JSON:API responses as well, in case the upstream format
    # changes again.
    if not themes:
        included = _included_index(result.get('included') or [])
        for anime in result.get('data') or []:
            for theme in _related(included, anime.get('relationships'), 'animethemes'):
                attrs = theme.get('attributes') or {}
                song = next(iter(_related(included, theme.get('relationships'), 'song')), None)
                if not song:
                    continue
                title = (song.get('attributes') or {}).get('title')
                if not title:
                    continue
                artists = []
                for artist in _related(included, song.get('relationships'), 'artists'):
                    name = (artist.get('attributes') or {}).get('name')
                    if name and name not in artists:
                        artists.append(name)
                entries = _related(included, theme.get('relationships'), 'animethemeentries')
                ranges = [str((entry.get('attributes') or {}).get('episodes') or '').strip()
                          for entry in entries]
                themes.append({'type': str(attrs.get('type') or '').upper(),
                               'sequence': attrs.get('sequence') or 0,
                               'title': title.strip(), 'artist': ', '.join(artists),
                               'episodes': [value for value in ranges if value]})
    return themes


def _themes(anilist_id):
    path = _cache_path(anilist_id)
    try:
        cached = json.loads(path.read_text(encoding='utf-8'))
        cached_themes = cached.get('themes')
        if cached_themes and time.time() - float(cached.get('fetched_at', 0)) < 30 * 24 * 60 * 60:
            return cached_themes
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    themes = _fetch_themes(anilist_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'fetched_at': time.time(), 'themes': themes},
                                    ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
    return themes


def _episode_matches(specification, episode_number):
    if not specification:
        return False
    for part in re.split(r'[,;]', specification):
        match = re.fullmatch(r'\s*(\d+)\s*(?:[-–~]\s*(\d+))?\s*', part)
        if match:
            start = int(match.group(1))
            end = int(match.group(2) or start)
            if start <= episode_number <= end:
                return True
    return False


def episode_tracks(anilist_id, episode_number):
    """Return this episode's OP and ED as Last.fm artist/track records."""
    if not anilist_id or not isinstance(episode_number, int) or episode_number < 1:
        return []
    themes = _themes(anilist_id)
    tracks = []
    for kind in ('OP', 'ED'):
        candidates = [theme for theme in themes if theme['type'].startswith(kind)]
        matching = [theme for theme in candidates
                    if any(_episode_matches(value, episode_number)
                           for value in theme['episodes'])]
        selected = matching or [theme for theme in candidates if not theme['episodes']]
        if not selected and candidates:
            selected = [candidates[0]]
        if selected:
            theme = sorted(selected, key=lambda item: item['sequence'])[0]
            if theme['artist']:
                tracks.append({'artist': theme['artist'], 'track': theme['title']})
    return tracks


def scrobble(api_key, api_secret, session_key, tracks, timestamp=None):
    if not tracks:
        return 0
    timestamp = int(timestamp or time.time())
    params = {'method': 'track.scrobble', 'api_key': api_key, 'sk': session_key}
    for index, track in enumerate(tracks):
        params[f'artist[{index}]'] = track['artist']
        params[f'track[{index}]'] = track['track']
        params[f'timestamp[{index}]'] = timestamp
        params[f'chosenByUser[{index}]'] = 1
    result = _api_call(params, api_secret, post=True)
    scrobbles = result.get('scrobbles') or {}
    accepted = int(scrobbles.get('@attr', {}).get('accepted', 0))
    if accepted < len(tracks):
        raise RuntimeError('O Last.fm não aceitou todos os temas desta reprodução.')
    return accepted
