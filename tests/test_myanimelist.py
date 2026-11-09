"""Offline tests for MyAnimeList authentication and progress reconciliation."""
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError
from urllib.request import urlopen

from anime.services import mal_callback, mal_sync, myanimelist
from anime.storage import settings, watch_progress


class MalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home_patch = patch.object(Path, 'home', return_value=Path(self.temp.name))
        self.home_patch.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.home_patch.stop)

    def connect(self):
        settings.set_mal_credentials(client_id='client', redirect_uri='http://localhost:8765/callback',
                                     access_token='access', refresh_token='refresh',
                                     expires_at=99999999999, username='alice')

    def test_oauth_uses_pkce_state_and_validates_callback(self):
        redirect = 'http://localhost:8765/callback'
        url, verifier, state = myanimelist.new_authorization('client', redirect)
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query['code_challenge'], [verifier])
        self.assertEqual(query['code_challenge_method'], ['plain'])
        self.assertEqual(myanimelist.callback_code(f'{redirect}?code=abc&state={state}', redirect, state), 'abc')
        with self.assertRaises(ValueError):
            myanimelist.callback_code(f'{redirect}?code=abc&state=wrong', redirect, state)
        with self.assertRaises(ValueError):
            myanimelist.callback_code(f'http://evil.test/callback?code=abc&state={state}', redirect, state)

    def test_loopback_callback_rejects_invalid_state_and_accepts_valid_code(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        redirect = f'http://127.0.0.1:{port}/callback'
        received = []
        done = threading.Event()
        listener = mal_callback.CallbackListener(
            redirect, 'expected', lambda code: (received.append(code), done.set()), 'Received', 'Invalid')
        self.addCleanup(listener.close)
        with self.assertRaises(HTTPError) as invalid:
            urlopen(redirect + '?code=bad&state=wrong', timeout=2)
        self.assertEqual(invalid.exception.code, 400)
        self.assertEqual(received, [])
        with urlopen(redirect + '?code=good&state=expected', timeout=2) as response:
            self.assertIn(b'Received', response.read())
        self.assertTrue(done.wait(2))
        self.assertEqual(received, ['good'])

    def test_callback_listener_rejects_non_loopback_addresses(self):
        with self.assertRaises(ValueError):
            mal_callback.CallbackListener('http://example.com:8765/callback', 's', lambda _: None, 'ok', 'error')

    def test_expired_token_refreshes_and_preserves_credentials(self):
        self.connect()
        settings.set_mal_credentials(expires_at=0, client_secret='secret')
        with patch.object(myanimelist, '_request', return_value={
                'access_token': 'new', 'refresh_token': 'new-refresh', 'expires_in': 3600}) as request:
            self.assertEqual(myanimelist.access_token(), 'new')
        self.assertEqual(request.call_args.args[1]['grant_type'], 'refresh_token')
        self.assertEqual(request.call_args.args[1]['client_secret'], 'secret')
        self.assertEqual(settings.mal_credentials()['refresh_token'], 'new-refresh')
        self.assertEqual(settings.mal_credentials()['username'], 'alice')
        self.assertEqual(settings.settings_path().stat().st_mode & 0o777, 0o600)

    def test_token_exchange_supports_clients_with_and_without_secret(self):
        with patch.object(myanimelist, '_request', return_value={}) as request:
            myanimelist.exchange_code('client', 'http://localhost/cb', 'verifier', 'code', 'secret')
            self.assertEqual(request.call_args.args[1]['client_secret'], 'secret')
            myanimelist.exchange_code('client', 'http://localhost/cb', 'verifier', 'code')
            self.assertNotIn('client_secret', request.call_args.args[1])

    def test_request_updates_only_progress_via_patch(self):
        self.connect()
        with patch.object(myanimelist, '_request', return_value={}) as request:
            myanimelist.set_progress(15, 3)
        self.assertEqual(request.call_args.kwargs['method'], 'PATCH')
        self.assertEqual(request.call_args.args[1], {'num_watched_episodes': 3})

    def test_list_status_reads_authenticated_detail_and_handles_absence(self):
        self.connect()
        status = {'status': 'watching', 'num_episodes_watched': 3, 'score': 8}
        with patch.object(myanimelist, '_request', return_value={'my_list_status': status}) as request:
            self.assertEqual(myanimelist.get_list_status(15), status)
            self.assertEqual(request.call_args.kwargs['token'], 'access')
            self.assertIn('fields=my_list_status', request.call_args.args[0])
        with patch.object(myanimelist, '_request', return_value={}):
            self.assertIsNone(myanimelist.get_list_status(15))

    def test_disconnect_during_refresh_does_not_restore_session(self):
        self.connect()
        settings.set_mal_credentials(expires_at=0)
        def refresh(*_args):
            myanimelist.disconnect()
            return {'access_token': 'new', 'refresh_token': 'new-refresh'}
        with patch.object(myanimelist, '_request', side_effect=refresh):
            with self.assertRaises(RuntimeError):
                myanimelist.access_token()
        self.assertFalse(settings.mal_credentials()['refresh_token'])

    def test_tracking_is_opt_in_and_scoped_to_account(self):
        self.connect()
        with patch.object(myanimelist, 'get_list_status') as get_status:
            self.assertFalse(mal_sync.sync({'id': 10, 'idMal': 20}, push_through=1))
            get_status.assert_not_called()
        self.assertTrue(mal_sync.set_tracked(10, True))
        self.assertTrue(mal_sync.is_tracked(10))
        settings.set_mal_credentials(username='bob')
        self.assertFalse(mal_sync.is_tracked(10))

    def test_open_tracked_anime_imports_without_remote_write(self):
        self.connect()
        mal_sync.set_tracked(10, True)
        watch_progress.mark_watched(10, 7)
        with patch.object(myanimelist, 'get_list_status', return_value={'num_episodes_watched': 4}), \
             patch.object(myanimelist, 'set_progress') as update:
            self.assertTrue(mal_sync.sync({'id': 10, 'idMal': 20}))
            self.assertEqual(watch_progress.watched_episodes(10), {1, 2, 3, 4, 7})
            update.assert_not_called()

    def test_automatic_tracking_never_decreases_large_remote_progress(self):
        self.connect()
        mal_sync.set_tracked(21, True)
        mal_sync.change(21, [1], False)
        with patch.object(myanimelist, 'get_list_status', return_value={'num_episodes_watched': 1000}), \
             patch.object(myanimelist, 'set_progress') as update:
            mal_sync.sync({'id': 21, 'idMal': 21}, push_through=1)
            update.assert_not_called()
        self.assertIn(1000, watch_progress.watched_episodes(21))

    def test_only_user_selected_new_progress_can_advance(self):
        self.connect()
        mal_sync.set_tracked(10, True)
        watch_progress.set_watched(10, range(1, 101), True)
        with patch.object(myanimelist, 'get_list_status', return_value={'num_episodes_watched': 4}), \
             patch.object(myanimelist, 'set_progress') as update:
            mal_sync.sync({'id': 10, 'idMal': 20}, push_through=5)
            update.assert_called_once_with(20, 5)

    def test_newer_remote_progress_is_never_overwritten_by_older_read(self):
        self.connect()
        mal_sync.set_tracked(21, True)
        watch_progress.set_watched(21, range(1, 11), True)
        with patch.object(myanimelist, 'get_list_status', side_effect=[
                {'num_episodes_watched': 2}, {'num_episodes_watched': 300}]), \
             patch.object(myanimelist, 'set_progress') as update:
            mal_sync.sync({'id': 21, 'idMal': 21}, push_through=10)
            update.assert_not_called()

    def test_queued_automatic_update_is_cancelled_by_manual_edit(self):
        self.connect()
        mal_sync.set_tracked(10, True)
        watch_progress.set_watched(10, range(1, 11), True)
        revision = mal_sync.revision(10, 'alice')
        mal_sync.reserve_manual_edit(10, 'alice')
        with patch.object(myanimelist, 'get_list_status', return_value={'num_episodes_watched': 2}), \
             patch.object(myanimelist, 'set_progress') as update:
            self.assertFalse(mal_sync.sync({'id': 10, 'idMal': 20}, push_through=10, expected_revision=revision))
            update.assert_not_called()

    def test_manual_edit_forwards_rewatch_and_can_lower_progress(self):
        self.connect()
        mal_sync.set_tracked(10, True)
        changes = {'num_watched_episodes': 3, 'is_rewatching': 'true', 'num_times_rewatched': 2}
        with patch.object(myanimelist, 'update_list_status') as update:
            mal_sync.save_manual(10, 20, 'alice', changes)
            update.assert_called_once_with(20, changes)
        mal_sync.set_tracked(10, False)
        with self.assertRaises(RuntimeError):
            mal_sync.save_manual(10, 20, 'alice', changes)
