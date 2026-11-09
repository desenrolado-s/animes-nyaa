"""MyAnimeList OAuth and authenticated anime-list API."""
import json
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from ..storage import settings

AUTH_URL = 'https://myanimelist.net/v1/oauth2/authorize'
TOKEN_URL = 'https://myanimelist.net/v1/oauth2/token'
API_URL = 'https://api.myanimelist.net/v2'
_token_lock = threading.RLock()


def new_authorization(client_id, redirect_uri):
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    query = urlencode({'response_type': 'code', 'client_id': client_id,
                       'redirect_uri': redirect_uri, 'code_challenge': verifier,
                       'code_challenge_method': 'plain', 'state': state})
    return AUTH_URL + '?' + query, verifier, state


def callback_code(callback_url, redirect_uri, state):
    actual, expected = urlparse(callback_url.strip()), urlparse(redirect_uri)
    if (actual.scheme, actual.netloc, actual.path) != (expected.scheme, expected.netloc, expected.path):
        raise ValueError('URL de redirecionamento inválida.')
    query = parse_qs(actual.query)
    if not secrets.compare_digest((query.get('state') or [''])[0], state):
        raise ValueError('O estado da autorização não corresponde. Tente autorizar novamente.')
    code = (query.get('code') or [''])[0]
    if not code:
        raise ValueError('A URL não contém um código de autorização.')
    return code


def _request(url, data=None, method=None, token=None):
    headers = {'Accept': 'application/json', 'User-Agent': 'AnimeNyaa/1.0'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        data = urlencode(data).encode('utf-8')
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read(2_000_000).decode('utf-8'))
    except HTTPError as error:
        raise RuntimeError(f'MyAnimeList: HTTP {error.code}') from error
    except (URLError, ValueError, OSError) as error:
        raise RuntimeError('Não foi possível acessar o MyAnimeList.') from error


def exchange_code(client_id, redirect_uri, verifier, code, client_secret=''):
    data = {'client_id': client_id, 'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri, 'code_verifier': verifier, 'code': code}
    if client_secret:
        data['client_secret'] = client_secret
    return _request(TOKEN_URL, data)


def save_tokens(client_id, redirect_uri, tokens, username=None, client_secret=None):
    access = tokens.get('access_token')
    refresh = tokens.get('refresh_token')
    if not access or not refresh:
        raise RuntimeError('MyAnimeList não retornou uma sessão válida.')
    changes = dict(client_id=client_id, redirect_uri=redirect_uri,
                   access_token=access, refresh_token=refresh,
                   expires_at=time.time() + int(tokens.get('expires_in', 3600)))
    if username is not None:
        changes['username'] = username
    if client_secret is not None:
        changes['client_secret'] = client_secret
    settings.set_mal_credentials(**changes)


def access_token():
    creds = settings.mal_credentials()
    if not creds['access_token'] or not creds['refresh_token']:
        raise RuntimeError('Conta MyAnimeList não conectada.')
    if creds['expires_at'] <= time.time() + 60:
        data = {'client_id': creds['client_id'], 'grant_type': 'refresh_token',
                'refresh_token': creds['refresh_token']}
        if creds['client_secret']:
            data['client_secret'] = creds['client_secret']
        tokens = _request(TOKEN_URL, data)
        with _token_lock:
            current = settings.mal_credentials()
            if current['refresh_token'] != creds['refresh_token']:
                raise RuntimeError('A conta MyAnimeList foi alterada.')
            save_tokens(creds['client_id'], creds['redirect_uri'], tokens)
            return tokens['access_token']
    return creds['access_token']


def disconnect():
    with _token_lock:
        settings.set_mal_credentials(access_token='', refresh_token='', expires_at=0, username='')


def user_name(token):
    return _request(API_URL + '/users/@me', token=token).get('name', '')


def get_progress(mal_id):
    result = _request(f'{API_URL}/anime/{int(mal_id)}?fields=my_list_status', token=access_token())
    status = result.get('my_list_status') or {}
    return max(0, int(status.get('num_episodes_watched') or 0))


def set_progress(mal_id, count):
    return _request(f'{API_URL}/anime/{int(mal_id)}/my_list_status',
                    {'num_watched_episodes': max(0, int(count))}, method='PATCH', token=access_token())
