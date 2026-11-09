"""Unit tests for anime detail layout persistence and tab navigation."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

try:
    import gi
    gi.require_version('Adw', '1')
    gi.require_version('Gtk', '4.0')
    from gi.repository import Adw, Gdk, Gtk
    HAS_GTK = bool(Gtk.init_check()) and Gdk.Display.get_default() is not None
    if HAS_GTK:
        Adw.init()
        from anime.application import AnimeApp
except (ImportError, ValueError, RuntimeError):
    HAS_GTK = False


@unittest.skipUnless(HAS_GTK, "GTK display is not available in headless offline test environment")
class DetailLayoutTests(unittest.TestCase):
    def setUp(self):
        self.app = AnimeApp(smoke=True)
        self.app.do_activate()
        self.sample_anime = {
            'id': 100,
            'title': {'romaji': 'Black Clover', 'english': 'Black Clover'},
            'episodes': 12,
            'format': 'TV',
            'seasonYear': 2017,
            'averageScore': 79,
            'genres': ['Action', 'Comedy', 'Fantasy'],
            'description': 'Asta and Yuno are orphans.',
        }
        self.app.open_anime(self.sample_anime)

    def test_anime_overview_is_persistent_in_paned_start_child(self):
        self.assertIsNotNone(self.app.anime_paned.get_start_child())
        self.assertEqual(self.app.anime_paned.get_end_child(), self.app.anime_tabs)
        self.assertEqual(self.app.anime_tabs.get_visible_child_name(), 'episodes')
        self.assertEqual(self.app.episode_tab_stack.get_visible_child_name(), 'episodes')

    def test_episode_search_keeps_overview_visible(self):
        with patch.object(self.app, 'search_releases'):
            self.app.search_episode(1)
        self.assertEqual(self.app.stack.get_visible_child_name(), 'anime')
        self.assertEqual(self.app.anime_tabs.get_visible_child_name(), 'episodes')
        self.assertEqual(self.app.episode_tab_stack.get_visible_child_name(), 'results')
        self.assertIsNotNone(self.app.anime_paned.get_start_child())

    def test_episode_context_menu_updates_both_lists_with_filter(self):
        from anime.storage import watch_progress
        from anime.ui.i18n import tr
        with tempfile.TemporaryDirectory() as home, patch.object(Path, 'home', return_value=Path(home)):
            self.app.populate_episodes(12)
            files = [{'name': f'Show - {n:02}.mkv', 'size': '1 GB', 'index': n}
                     for n in range(1, 5)]
            self.app.finish_batch_episodes(files, None, {'title': 'Batch'})
            self.app.episode_search.set_text('04')
            self.app.filter_episodes()
            row = self.app.episode_rows[0][1]
            gesture = next(c for c in row.observe_controllers() if isinstance(c, Gtk.GestureClick) and c.get_button() == 3)
            gesture.emit('pressed', 1, 10.0, 10.0)
            child = row.get_first_child()
            while child and not isinstance(child, Gtk.Popover):
                child = child.get_next_sibling()
            self.assertIsNotNone(child)
            box = child.get_child()
            box.get_first_child().get_next_sibling().emit('clicked')
            self.assertEqual(watch_progress.watched_episodes(100), {1, 2, 3})
            self.assertTrue(self.app.batch_watched_badges[2][0].get_visible())
            self.assertFalse(self.app.episode_watched_badges[4].get_visible())
            gesture.emit('pressed', 1, 10.0, 10.0)
            child = row.get_first_child()
            while child and not isinstance(child, Gtk.Popover):
                child = child.get_next_sibling()
            child.get_child().get_first_child().emit('clicked')
            self.assertEqual(watch_progress.watched_episodes(100), {1, 2, 3, 4})
            self.assertTrue(self.app.batch_watched_badges[4][0].get_visible())
            self.app.batch_episode_search.set_text('04')
            self.app.filter_batch_episodes()
            batch_row = self.app.batch_episode_rows[0][2]
            batch_gesture = next(c for c in batch_row.observe_controllers()
                                 if isinstance(c, Gtk.GestureClick) and c.get_button() == 3)
            batch_gesture.emit('pressed', 1, 10.0, 10.0)
            menu = batch_row.get_first_child()
            while menu and not isinstance(menu, Gtk.Popover):
                menu = menu.get_next_sibling()
            self.assertIsNotNone(menu)
            self.assertEqual(menu.get_child().get_first_child().get_label(), tr('Marcar como não assistido'))
            menu.get_child().get_last_child().emit('clicked')
            self.assertEqual(watch_progress.watched_episodes(100), {4})

    def test_returning_from_results_restores_episode_list(self):
        with patch.object(self.app, 'search_releases'):
            self.app.search_episode(2)
        self.assertEqual(self.app.episode_tab_stack.get_visible_child_name(), 'results')
        self.app.show_anime()
        self.assertEqual(self.app.episode_tab_stack.get_visible_child_name(), 'episodes')
        self.assertIsNotNone(self.app.anime_paned.get_start_child())

    def test_batch_tab_and_subviews_keep_overview_visible(self):
        self.app.anime_tabs.set_visible_child_name('batches')
        self.assertEqual(self.app.batch_view.get_visible_child_name(), 'catalog')
        self.assertIsNotNone(self.app.anime_paned.get_start_child())

        # Simulate viewing batch episodes
        self.app.batch_view.set_visible_child_name('episodes')
        self.assertIsNotNone(self.app.anime_paned.get_start_child())

        # Return to batch catalog
        self.app.batch_view.set_visible_child_name('catalog')
        self.assertIsNotNone(self.app.anime_paned.get_start_child())

    def test_open_anime_resets_navigation_subviews(self):
        with patch.object(self.app, 'search_releases'):
            self.app.search_episode(5)
        self.assertEqual(self.app.episode_tab_stack.get_visible_child_name(), 'results')
        self.app.anime_tabs.set_visible_child_name('batches')
        self.app.batch_view.set_visible_child_name('episodes')

        # Reopen anime
        self.app.open_anime(self.sample_anime)
        self.assertEqual(self.app.anime_tabs.get_visible_child_name(), 'episodes')
        self.assertEqual(self.app.episode_tab_stack.get_visible_child_name(), 'episodes')
        self.assertEqual(self.app.batch_view.get_visible_child_name(), 'catalog')

    def test_finish_releases_handles_none_active_episode(self):
        self.app.active_episode = None
        releases = [{'title': 'Release 1', 'size': '1 GB', 'seeders': '10', 'leechers': '2', 'downloads': '5', 'magnet': 'magnet:?'}]
        self.app.finish_releases(releases, None)
        self.assertEqual(len(self.app.results), 1)

    def test_finish_releases_handles_valid_active_episode(self):
        self.app.active_episode = 1
        releases = [{'title': 'Release 1', 'size': '1 GB', 'seeders': '10', 'leechers': '2', 'downloads': '5', 'magnet': 'magnet:?'}]
        self.app.finish_releases(releases, None)
        self.assertEqual(len(self.app.results), 1)

    def test_finish_releases_handles_special_markup_characters(self):
        self.app.active_episode = 1
        special_title = '1[喵萌奶茶屋&VCB-Studio] 夏日重现 / Summer Time Rendering <1080p>'
        releases = [{'title': special_title, 'size': '1.3 GiB & fast', 'seeders': '10', 'leechers': '2', 'downloads': '5', 'magnet': 'magnet:?'}]
        self.app.finish_releases(releases, None)
        self.assertEqual(len(self.app.results), 1)
        row = self.app.release_list.get_row_at_index(0)
        self.assertEqual(row.get_title(), special_title)
        self.assertEqual(row.get_subtitle(), '1.3 GiB & fast   ·   5 downloads')

    def test_episode_subtitles_consistency_and_special_chars(self):
        row0 = self.app.episode_list.get_row_at_index(0)
        self.assertEqual(row0.get_title(), 'Episódio 01')
        self.assertEqual(row0.get_subtitle(), 'Pesquisar releases no Nyaa')

        self.app.finish_episode_titles(self.sample_anime['id'], {1: 'Asta & Yuno <Magic>'})
        self.assertEqual(row0.get_title(), 'Episódio 01')
        self.assertEqual(row0.get_subtitle(), 'Asta & Yuno <Magic>')

        self.app.filter_episodes()
        refreshed_row0 = self.app.episode_list.get_row_at_index(0)
        self.assertEqual(refreshed_row0.get_title(), 'Episódio 01')
        self.assertEqual(refreshed_row0.get_subtitle(), 'Asta & Yuno <Magic>')

    def test_anime_overview_and_panels_have_proper_margins_and_padding(self):
        self.assertGreater(self.app.anime_poster.get_margin_top(), 0)
        episode_panel = self.app.episode_tab_stack.get_child_by_name('episodes')
        self.assertGreaterEqual(episode_panel.get_margin_top(), 10)
        self.assertGreaterEqual(episode_panel.get_margin_start(), 12)
        batch_catalog = self.app.batch_view.get_child_by_name('catalog')
        self.assertGreaterEqual(batch_catalog.get_margin_top(), 10)
        self.assertGreaterEqual(batch_catalog.get_margin_start(), 12)

    def test_search_traces_use_popovers_without_expanding_card(self):
        self.assertFalse(self.app.search_info_button.get_visible())
        self.assertFalse(self.app.batch_search_info_button.get_visible())

        self.app.update_search_trace('Consultas: Q1 · Q2 · Q3 · Q4')
        self.assertEqual(self.app.search_trace.get_text(), 'Consultas: Q1 · Q2 · Q3 · Q4')
        self.assertTrue(self.app.search_info_button.get_visible())

        self.app.update_search_trace('')
        self.assertFalse(self.app.search_info_button.get_visible())

    def test_playback_notification_card_has_proper_padding(self):
        playback_card = self.app.playback_revealer.get_child()
        self.assertIsNotNone(playback_card)
        self.assertTrue(playback_card.has_css_class('card'))

        playback_content = playback_card.get_first_child()
        self.assertIsNotNone(playback_content)
        self.assertGreaterEqual(playback_content.get_margin_top(), 10)
        self.assertGreaterEqual(playback_content.get_margin_bottom(), 10)
        self.assertGreaterEqual(playback_content.get_margin_start(), 12)
        self.assertGreaterEqual(playback_content.get_margin_end(), 12)
        self.assertGreaterEqual(playback_content.get_spacing(), 12)

