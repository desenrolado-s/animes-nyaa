"""Offline tests for the application's parsing and local persistence."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anime.services import lastfm, nyaa, torrent
from anime.storage import history, lastfm_progress, settings, watch_progress
from anime.ui.i18n import tr


class SearchParsingTests(unittest.TestCase):
    def test_nyaa_search_parses_torrent_row(self):
        html = '''<table><tr><td>Anime</td><td><a href="/view/1">[Group] Show - 01</a></td>
        <td><a href="magnet:?xt=urn:btih:abc">magnet</a></td><td>1 GiB</td>
        <td>today</td><td>42</td><td>3</td><td>100</td></tr></table>'''
        parser = nyaa._SearchParser()
        parser.feed(html)
        self.assertEqual(parser.rows, [{
            'title': '[Group] Show - 01', 'magnet': 'magnet:?xt=urn:btih:abc',
            'size': '1 GiB', 'date': 'today', 'seeders': '42',
            'leechers': '3', 'downloads': '100',
        }])

    def test_episode_matching_and_batch_detection(self):
        self.assertTrue(nyaa.matches_episode('Show S02E003 1080p', 3))
        self.assertFalse(nyaa.matches_episode('Show S02E013 1080p', 3))
        self.assertTrue(nyaa.is_batch_title('Show Complete 01-24'))

    def test_torrent_listing_filters_video_files_and_finds_episode(self):
        result = type('Result', (), {'returncode': 0,
                                    'stdout': '0 Show/Show - 01.mkv (1 GB)\n1 notes.txt (1 KB)\n',
                                    'stderr': ''})()
        with patch.object(torrent.shutil, 'which', return_value='/usr/bin/webtorrent'), \
                patch.object(torrent.subprocess, 'run', return_value=result):
            self.assertEqual(torrent.list_video_files('magnet:test'), [
                {'index': 0, 'name': 'Show/Show - 01.mkv', 'size': '1 GB'}
            ])
        self.assertEqual(torrent.episode_number('Show S02E03.mkv'), 3)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.patcher = patch.object(Path, 'home', return_value=self.home)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def test_settings_preserve_existing_values_and_secure_credentials(self):
        settings.set_temporary_directory('/tmp/media')
        settings.set_lastfm_credentials('key', 'secret', session_key='session',
                                        username='listener', enabled=False)
        self.assertEqual(settings.temporary_directory(), Path('/tmp/media'))
        self.assertEqual(settings.lastfm_credentials()['username'], 'listener')
        self.assertFalse(settings.lastfm_credentials()['enabled'])
        self.assertEqual(settings.settings_path().stat().st_mode & 0o777, 0o600)

    def test_watch_progress_and_history_round_trip(self):
        self.assertTrue(watch_progress.mark_watched(12, 4))
        self.assertEqual(watch_progress.watched_episodes(12), {4})
        item = {'title': 'Release', 'magnet': 'magnet:test'}
        history.record(item, {'id': 12, 'display_title': 'Show'},
                       file_index=3, file_name='Show - 04.mkv', episode_number=4)
        entry = history.load()[0]
        self.assertEqual(entry['episode_number'], 4)
        self.assertEqual(entry['anilist_id'], 12)

    def test_lastfm_progress_claim_can_retry_until_submitted(self):
        self.assertTrue(lastfm_progress.claim(12, 4))
        self.assertFalse(lastfm_progress.claim(12, 4))
        lastfm_progress.release(12, 4)
        self.assertTrue(lastfm_progress.claim(12, 4))
        lastfm_progress.mark_submitted(12, 4)
        self.assertFalse(lastfm_progress.claim(12, 4))


class LastFmTests(unittest.TestCase):
    def test_episode_range_selection_returns_opening_and_ending(self):
        themes = [
            {'type': 'OP', 'sequence': 1, 'title': 'Opening', 'artist': 'Singer', 'episodes': ['1-12']},
            {'type': 'ED', 'sequence': 1, 'title': 'Ending', 'artist': 'Band', 'episodes': ['7-12']},
        ]
        with patch.object(lastfm, '_themes', return_value=themes):
            self.assertEqual(lastfm.episode_tracks(99, 8), [
                {'artist': 'Singer', 'track': 'Opening'},
                {'artist': 'Band', 'track': 'Ending'},
            ])

    def test_authorization_url_encodes_token(self):
        self.assertIn('token=a+b', lastfm.authorization_url('key', 'a b'))


class PlaybackStatusTests(unittest.TestCase):
    def test_status_translations(self):
        settings.set_language('en')
        self.assertEqual(tr('Cancelar reprodução'), 'Cancel playback')
        self.assertEqual(tr('Conectando ao WebTorrent…'), 'Connecting to WebTorrent…')
        self.assertEqual(tr('Conectando aos peers do torrent…'), 'Connecting to torrent peers…')
        self.assertEqual(tr('Conectado a 5 peer(s)…'), 'Connected to 5 peer(s)…')
        self.assertEqual(tr('Reproduzindo no mpv'), 'Playing in mpv')
        self.assertEqual(tr('Reprodução cancelada.'), 'Playback cancelled.')
        settings.set_language('pt')
        self.assertEqual(tr('Cancelar reprodução'), 'Cancelar reprodução')

    def test_session_isolation_ignores_stale_events(self):
        from unittest.mock import MagicMock
        from anime.application import AnimeApp
        app = AnimeApp(smoke=True)
        app.current_playback_session_id = 2
        app.playback_status_label = MagicMock()
        # Stale event for session 1 should be ignored
        app.update_playback_status('Old message', is_playing=False, session_id=1)
        app.playback_status_label.set_text.assert_not_called()
        # Current event for session 2 should be applied
        app.update_playback_status('New message', is_playing=False, session_id=2)
        app.playback_status_label.set_text.assert_called_with('New message')


if __name__ == '__main__':
    unittest.main()
