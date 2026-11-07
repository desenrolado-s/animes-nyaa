"""Unit tests for anime detail layout persistence and tab navigation."""
import unittest
from unittest.mock import patch

import gi
gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gtk

Adw.init()
from anime.application import AnimeApp


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
