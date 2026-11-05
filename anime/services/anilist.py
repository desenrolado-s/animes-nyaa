"""Public AniList GraphQL catalogue client."""
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API_URL = 'https://graphql.anilist.co'
PER_PAGE = 20

_MEDIA_FIELDS = '''
  id
  idMal
  title { romaji english native }
  coverImage { large medium }
  format
  status
  seasonYear
  episodes
  nextAiringEpisode { episode }
  averageScore
  description(asHtml: false)
  genres
  siteUrl
'''

_TRENDING_QUERY = f'''
query ($page: Int, $perPage: Int) {{
  Page(page: $page, perPage: $perPage) {{
    pageInfo {{ hasNextPage currentPage }}
    media(type: ANIME, sort: [TRENDING_DESC, POPULARITY_DESC], isAdult: false) {{
      {_MEDIA_FIELDS}
    }}
  }}
}}
'''

_SEARCH_QUERY = f'''
query ($page: Int, $perPage: Int, $search: String) {{
  Page(page: $page, perPage: $perPage) {{
    pageInfo {{ hasNextPage currentPage }}
    media(type: ANIME, search: $search, sort: [SEARCH_MATCH, POPULARITY_DESC], isAdult: false) {{
      {_MEDIA_FIELDS}
    }}
  }}
}}
'''

_ID_MAL_QUERY = '''
query ($id: Int) {
  Media(id: $id, type: ANIME) { id idMal }
}
'''


def _query(query, variables):
    payload = json.dumps({'query': query, 'variables': variables}).encode('utf-8')
    request = Request(API_URL, data=payload, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'AnimeNyaa/1.0',
    })
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read(2_000_000).decode('utf-8'))
    except HTTPError as error:
        if error.code == 429:
            raise RuntimeError('AniList limitou temporariamente as consultas. Aguarde um pouco e tente novamente.') from error
        raise RuntimeError(f'AniList respondeu com HTTP {error.code}.') from error
    if result.get('errors'):
        messages = '; '.join(error.get('message', 'Erro GraphQL') for error in result['errors'])
        raise RuntimeError(messages)
    page = result.get('data', {}).get('Page') or {}
    return page.get('media', []), page.get('pageInfo', {})


def trending(page=1):
    return _query(_TRENDING_QUERY, {'page': page, 'perPage': PER_PAGE})


def search(title, page=1):
    title = title.strip()
    if not title:
        return [], {'hasNextPage': False, 'currentPage': page}
    return _query(_SEARCH_QUERY, {'page': page, 'perPage': PER_PAGE, 'search': title})


def mal_id(media_id):
    """Resolve the MyAnimeList ID for older saved entries missing idMal."""
    payload = json.dumps({'query': _ID_MAL_QUERY, 'variables': {'id': int(media_id)}}).encode('utf-8')
    request = Request(API_URL, data=payload, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'AnimeNyaa/1.0',
    })
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read(1_000_000).decode('utf-8'))
    except HTTPError as error:
        if error.code == 429:
            raise RuntimeError('AniList limitou temporariamente as consultas. Aguarde um pouco e tente novamente.') from error
        raise RuntimeError(f'AniList respondeu com HTTP {error.code}.') from error
    if result.get('errors'):
        messages = '; '.join(error.get('message', 'Erro GraphQL') for error in result['errors'])
        raise RuntimeError(messages)
    media = result.get('data', {}).get('Media') or {}
    return media.get('idMal')


def display_title(media):
    titles = media.get('title') or {}
    return titles.get('english') or titles.get('romaji') or titles.get('native') or 'Anime sem título'


def torrent_query(media):
    titles = media.get('title') or {}
    return titles.get('english') or titles.get('romaji') or titles.get('native') or ''


def episode_count(media):
    count = media.get('episodes')
    if count:
        return min(int(count), 1000)
    airing = media.get('nextAiringEpisode') or {}
    upcoming = airing.get('episode')
    return min(max(int(upcoming) - 1, 0), 1000) if upcoming else 0
