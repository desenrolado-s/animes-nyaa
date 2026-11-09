"""Offline tests for MyAnimeList authentication and progress reconciliation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from anime.services import mal_sync, myanimelist
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

    def test_expired_token_refreshes_and_preserves_credentials(self):
        self.connect()
        settings.set_mal_credentials(expires_at=0)
        with patch.object(myanimelist, '_request', return_value={
                'access_token': 'new', 'refresh_token': 'new-refresh', 'expires_in': 3600}) as request:
            self.assertEqual(myanimelist.access_token(), 'new')
        self.assertEqual(request.call_args.args[1]['grant_type'], 'refresh_token')
        self.assertEqual(settings.mal_credentials()['refresh_token'], 'new-refresh')
        self.assertEqual(settings.mal_credentials()['username'], 'alice')
        self.assertEqual(settings.settings_path().stat().st_mode & 0o777, 0o600)

    def test_request_updates_only_progress_via_patch(self):
        self.connect()
        with patch.object(myanimelist, '_request', return_value={}) as request:
            myanimelist.set_progress(15, 3)
        self.assertEqual(request.call_args.kwargs['method'], 'PATCH')
        self.assertEqual(request.call_args.args[1], {'num_watched_episodes': 3})

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

    def test_pending_changes_are_scoped_to_account(self):
        self.connect()
        mal_sync.change(10, [1], False)
        alice_pending = mal_sync._pending_path()
        settings.set_mal_credentials(username='bob')
        self.assertNotEqual(alice_pending, mal_sync._pending_path())
        self.assertEqual(mal_sync._load_pending(), {})

    def test_import_and_manual_changes_preserve_gaps_and_remote_progress(self):
        self.connect()
        watch_progress.mark_watched(10, 7)
        with patch.object(myanimelist, 'get_progress', return_value=4), \
             patch.object(myanimelist, 'set_progress') as update:
            self.assertTrue(mal_sync.sync({'id': 10, 'idMal': 20}))
            self.assertEqual(watch_progress.watched_episodes(10), {1, 2, 3, 4, 7})
            update.assert_not_called()
        mal_sync.change(10, [3], False)
        with patch.object(myanimelist, 'get_progress', return_value=4), \
             patch.object(myanimelist, 'set_progress') as update:
            mal_sync.sync({'id': 10, 'idMal': 20})
            update.assert_called_once_with(20, 2)
            self.assertEqual(watch_progress.watched_episodes(10), {1, 2, 4, 7})

    def test_failed_update_retries_pending_without_reimporting_unwatched(self):
        self.connect()
        watch_progress.set_watched(10, range(1, 5), True)
        mal_sync.change(10, [2], False)
        with patch.object(myanimelist, 'get_progress', return_value=4), \
             patch.object(myanimelist, 'set_progress', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                mal_sync.sync({'id': 10, 'idMal': 20})
        with patch.object(myanimelist, 'get_progress', return_value=4), \
             patch.object(myanimelist, 'set_progress') as update:
            mal_sync.sync({'id': 10, 'idMal': 20})
            update.assert_called_once_with(20, 1)
            self.assertNotIn(2, watch_progress.watched_episodes(10))

    def test_edits_during_request_are_not_lost(self):
        self.connect()
        def remote_update(_mal_id, _count):
            mal_sync.change(10, [1], False)
        mal_sync.change(10, [1, 2], True)
        with patch.object(myanimelist, 'get_progress', return_value=0), \
             patch.object(myanimelist, 'set_progress', side_effect=remote_update):
            mal_sync.sync({'id': 10, 'idMal': 20})
        with patch.object(myanimelist, 'get_progress', return_value=2), \
             patch.object(myanimelist, 'set_progress') as update:
            mal_sync.sync({'id': 10, 'idMal': 20})
            update.assert_called_once_with(20, 0)
            self.assertEqual(watch_progress.watched_episodes(10), {2})

    def test_remote_reduction_is_imported_after_initial_sync(self):
        self.connect()
        with patch.object(myanimelist, 'get_progress', return_value=4), \
             patch.object(myanimelist, 'set_progress'):
            mal_sync.sync({'id': 10, 'idMal': 20})
        watch_progress.mark_watched(10, 7)
        with patch.object(myanimelist, 'get_progress', return_value=2), \
             patch.object(myanimelist, 'set_progress') as update:
            mal_sync.sync({'id': 10, 'idMal': 20})
            self.assertEqual(watch_progress.watched_episodes(10), {1, 2, 7})
            update.assert_not_called()
