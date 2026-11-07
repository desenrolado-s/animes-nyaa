"""Anime overview, searchable episode list and batch navigation."""
from concurrent.futures import Future
from html.parser import HTMLParser
from html import unescape
import threading

import gi
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')
from gi.repository import Adw, Gdk, GLib, Gtk, Pango

from ..services import anilist, episode_titles
from ..storage import library, watch_progress
from .common import IMAGE_POOL
from .i18n import tr


EPISODE_RENDER_BATCH_SIZE = 40


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


class DetailUI:
    def build_anime_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        nav = Gtk.Box(spacing=12, valign=Gtk.Align.CENTER)
        back = Gtk.Button.new_from_icon_name('go-previous-symbolic')
        back.add_css_class('flat')
        back.set_tooltip_text(tr('Voltar ao catálogo'))
        back.connect('clicked', lambda *_: self.show_catalog())
        nav.append(back)
        self.anime_tabs = Adw.ViewStack(vexpand=True, hexpand=True)
        self.anime_switcher = Adw.ViewSwitcher(stack=self.anime_tabs)
        self.anime_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        self.anime_switcher.set_hexpand(True)
        self.anime_switcher.set_halign(Gtk.Align.CENTER)
        nav.append(self.anime_switcher)
        self.anime_tabs.connect('notify::visible-child-name', self.anime_view_changed)
        page.append(nav)

        self.episode_tab_stack = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.episode_tab_stack.add_named(self.build_episode_panel(), 'episodes')
        self.episode_tab_stack.add_named(self.build_results_page(), 'results')
        self.anime_tabs.add_titled(self.episode_tab_stack, 'episodes', tr('Episódios'))

        self.batch_view = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        batch_catalog_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        batch_catalog_page.set_margin_top(8)
        batch_catalog_page.set_margin_bottom(8)
        batch_catalog_page.set_margin_start(8)
        batch_catalog_page.set_margin_end(8)
        batch_search_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        batch_search_card.add_css_class('card')
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(batch_search_card, 'set_margin_' + side)(4)

        header_box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        header_box.append(Gtk.Image.new_from_icon_name('folder-videos-symbolic'))
        search_card_title = self.label(tr('Pesquisar batches no Nyaa'), 'caption-heading')
        search_card_title.set_hexpand(True)
        header_box.append(search_card_title)
        batch_search_card.append(header_box)

        batch_search_row = Gtk.Box(spacing=8)
        self.batch_search_query = Gtk.Entry(placeholder_text=tr('Consulta de batches no Nyaa'), hexpand=True)
        self.batch_search_query.set_activates_default(True)
        self.batch_search_query.connect('activate', lambda *_: self.search_edited_batches())
        batch_search_row.append(self.batch_search_query)
        search_btn = self.button(tr('Buscar batches'), self.search_edited_batches)
        search_btn.add_css_class('suggested-action')
        batch_search_row.append(search_btn)
        batch_search_card.append(batch_search_row)

        self.batch_search_extra = Gtk.Entry(placeholder_text=tr('Padrão adicional (opcional)'), hexpand=True)
        self.batch_search_extra.set_visible(False)
        batch_search_card.append(self.batch_search_extra)

        pattern_actions = Gtk.Box(spacing=8)
        pattern_btn = self.button(tr('＋ Adicionar padrão'), self.toggle_batch_pattern)
        pattern_btn.add_css_class('flat')
        pattern_actions.append(pattern_btn)
        batch_search_card.append(pattern_actions)

        self.batch_search_trace = self.label('', 'dim-label')
        self.batch_search_trace.set_margin_start(4)
        batch_search_card.append(self.batch_search_trace)
        batch_catalog_page.append(batch_search_card)

        self.batch_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.batch_list.add_css_class('boxed-list')
        self.batch_list.set_placeholder(Adw.StatusPage(
            icon_name='folder-videos-symbolic',
            title=tr('Nenhum batch salvo ainda'),
            description=tr('Use “Buscar batches” para procurar releases no Nyaa.'),
        ))
        self.batch_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.batch_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.batch_scroll.set_child(self.batch_list)
        self._connect_scroll_loader(self.batch_scroll, self.load_more_batch_rows)
        batch_catalog_page.append(self.batch_scroll)
        self.batch_view.add_named(batch_catalog_page, 'catalog')

        batch_episodes_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        batch_episodes_page.set_margin_top(8)
        batch_episodes_page.set_margin_bottom(8)
        batch_episodes_page.set_margin_start(8)
        batch_episodes_page.set_margin_end(8)
        batch_nav = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        back_to_batches = Gtk.Button.new_from_icon_name('go-previous-symbolic')
        back_to_batches.add_css_class('flat')
        back_to_batches.set_tooltip_text(tr('Voltar aos batches'))
        back_to_batches.connect('clicked', lambda *_: self.batch_view.set_visible_child_name('catalog'))
        batch_nav.append(back_to_batches)
        self.batch_episode_heading = self.label('')
        self.batch_episode_heading.add_css_class('title-3')
        self.batch_episode_heading.set_hexpand(True)
        self.batch_episode_heading.set_max_width_chars(56)
        self.batch_episode_heading.set_ellipsize(Pango.EllipsizeMode.END)
        batch_nav.append(self.batch_episode_heading)
        self.batch_episode_count = self.label('', 'dim-label')
        batch_nav.append(self.batch_episode_count)
        batch_episodes_page.append(batch_nav)

        self.batch_episode_files = []
        self.batch_filtered_files = []
        self.batch_episode_filter_query = ''
        self.batch_files_rendered = 0
        self.batch_episode_search = Gtk.SearchEntry(placeholder_text=tr('Filtrar arquivos do batch…'))
        self.batch_episode_search.set_search_delay(120)
        self.batch_episode_search.connect('search-changed', self.filter_batch_episodes)
        batch_episodes_page.append(self.batch_episode_search)

        self.batch_episode_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.batch_episode_list.add_css_class('boxed-list')
        self.batch_episode_list.set_vexpand(True)
        no_batch_matches = self.label('Nenhum episódio corresponde à busca.', 'dim-label')
        no_batch_matches.set_margin_top(24)
        no_batch_matches.set_halign(Gtk.Align.CENTER)
        self.batch_episode_list.set_placeholder(no_batch_matches)
        self.batch_episode_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.batch_episode_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.batch_episode_scroll.set_child(self.batch_episode_list)
        self._connect_scroll_loader(self.batch_episode_scroll, self.load_more_batch_episodes)
        batch_episodes_page.append(self.batch_episode_scroll)
        self.batch_episode_rows = []
        self.batch_view.add_named(batch_episodes_page, 'episodes')
        self.anime_tabs.add_titled(self.batch_view, 'batches', 'Batches')

        anime_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True,
                                vexpand=True, hexpand=True)
        anime_paned.set_resize_start_child(False)
        anime_paned.set_resize_end_child(True)
        anime_paned.set_shrink_start_child(False)
        anime_paned.set_position(390)
        anime_paned.set_start_child(self.build_anime_overview())
        anime_paned.set_end_child(self.anime_tabs)
        self.anime_paned = anime_paned
        page.append(anime_paned)
        return page

    def build_anime_overview(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.set_size_request(340, -1)
        panel.set_margin_end(8)
        panel.add_css_class('card')
        panel.set_margin_top(8)
        panel.set_margin_bottom(8)
        panel.set_margin_start(8)

        self.anime_poster = Gtk.Picture()
        self.anime_poster.set_size_request(180, 250)
        self.anime_poster.set_content_fit(Gtk.ContentFit.COVER)
        self.anime_poster.set_can_shrink(True)
        self.anime_poster.set_halign(Gtk.Align.CENTER)
        self.anime_poster.add_css_class('card')
        self.anime_poster.set_margin_start(12)
        self.anime_poster.set_margin_end(12)
        panel.append(self.anime_poster)

        self.anime_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.anime_info.set_margin_top(14)
        self.anime_info.set_margin_bottom(18)
        self.anime_info.set_margin_start(22)
        self.anime_info.set_margin_end(22)
        panel.append(self.anime_info)

        self.overview_title = self.label('', 'title-1')
        self.overview_title.set_justify(Gtk.Justification.CENTER)
        self.overview_title.set_xalign(0.5)
        self.overview_title.set_max_width_chars(30)
        self.anime_info.append(self.overview_title)

        self.anime_metadata = self.label('', 'dim-label')
        self.anime_metadata.set_justify(Gtk.Justification.CENTER)
        self.anime_metadata.set_xalign(0.5)
        self.anime_info.append(self.anime_metadata)

        self.anime_genres = self.label('', 'dim-label')
        self.anime_genres.set_justify(Gtk.Justification.CENTER)
        self.anime_genres.set_xalign(0.5)
        self.anime_info.append(self.anime_genres)

        self.my_list_button = self.button('＋ Minha lista', self.toggle_current_anime_in_list)
        self.anime_info.append(self.my_list_button)

        summary_heading = self.label('SINOPSE', 'caption-heading')
        self.anime_info.append(summary_heading)
        self.anime_summary = self.label('')
        self.anime_summary.set_lines(4)
        self.anime_summary.set_ellipsize(Pango.EllipsizeMode.END)
        self.anime_info.append(self.anime_summary)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(panel)
        return scroller

    def build_episode_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.set_margin_top(8)
        panel.set_margin_bottom(8)
        panel.set_margin_start(8)
        panel.set_margin_end(8)

        heading = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        title = self.label('Episódios', 'title-2')
        title.set_hexpand(True)
        heading.append(title)
        self.episode_count_label = self.label('', 'dim-label')
        heading.append(self.episode_count_label)
        panel.append(heading)

        self.episode_count = 0
        self.current_episode_titles = {}
        self.episode_filter_query = ''
        self.episode_filtered_numbers = []
        self.episode_rendered_count = 0
        self.episode_search = Gtk.SearchEntry(placeholder_text=tr('Filtrar episódios…'))
        self.episode_search.set_search_delay(120)
        self.episode_search.connect('search-changed', self.filter_episodes)
        panel.append(self.episode_search)

        self.episode_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.episode_list.add_css_class('boxed-list')
        self.episode_list.set_vexpand(True)
        no_episode_matches = self.label('Nenhum episódio corresponde à busca.', 'dim-label')
        no_episode_matches.set_margin_top(24)
        no_episode_matches.set_halign(Gtk.Align.CENTER)
        self.episode_list.set_placeholder(no_episode_matches)
        self.episode_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.episode_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.episode_scroll.set_child(self.episode_list)
        self._connect_scroll_loader(self.episode_scroll, self.load_more_episodes)
        self.episode_content = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.episode_content.add_named(self.episode_scroll, 'list')
        empty_state = Adw.StatusPage(
            icon_name='view-list-symbolic',
            title=tr('Episódios indisponíveis'),
            description=tr('AniList não informa a quantidade de episódios. Confira os batches disponíveis.'),
        )
        empty_state.set_child(self.button('Ver batches', lambda: self.anime_tabs.set_visible_child_name('batches')))
        self.episode_content.add_named(empty_state, 'empty')
        panel.append(self.episode_content)
        self.episode_rows = []
        return panel

    def open_anime(self, media):
        self.current_anime = dict(media)
        self.current_anime['display_title'] = anilist.display_title(media)
        self.current_episode_titles = {}
        self.update_my_list_button()
        self.query.set_text(self.current_anime['display_title'])
        self.overview_title.set_text(self.current_anime['display_title'])

        count = anilist.episode_count(media)
        self.episode_count_label.set_text(tr(f'{count} eps.') if count else tr('Episódios'))
        self.anime_metadata.set_text(self.anime_meta_text(media, count))
        genres = media.get('genres') or []
        self.anime_genres.set_text('  ·  '.join(genres[:5]))
        self.anime_summary.set_text(self.plain_description(media.get('description') or '') or
                                    tr('Sinopse indisponível.'))
        self.load_anime_poster(media)

        if hasattr(self, 'episode_tab_stack'):
            self.episode_tab_stack.set_visible_child_name('episodes')
        self.anime_tabs.set_visible_child_name('episodes')
        self.batch_view.set_visible_child_name('catalog')
        self.batch_search_query.set_text('')
        self.batch_search_trace.set_text('')
        self.batch_search_performed = False
        self.populate_episodes(count)
        self.refresh_watched_episodes()
        self.fetch_episode_titles(media)
        self.stack.set_visible_child_name('anime')
        self.show_notice(tr(f'{count} episódios no catálogo.') if count else
                    tr('AniList não informa o total de episódios; você ainda pode buscar batches.'))

    def fetch_episode_titles(self, media):
        media_id = media.get('id')
        mal_id = media.get('idMal')

        def worker():
            resolved_mal_id = mal_id
            if not resolved_mal_id and media_id:
                try:
                    resolved_mal_id = anilist.mal_id(media_id)
                except Exception:
                    resolved_mal_id = None
            titles = episode_titles.get_episode_titles(resolved_mal_id) if resolved_mal_id else {}
            GLib.idle_add(self.finish_episode_titles, media_id, titles, resolved_mal_id)

        threading.Thread(target=worker, daemon=True).start()

    def finish_episode_titles(self, media_id, titles, mal_id=None):
        if not self.current_anime or self.current_anime.get('id') != media_id:
            return False
        if mal_id and not self.current_anime.get('idMal'):
            self.current_anime['idMal'] = mal_id
            library.update_anime_metadata(self.current_anime)
        self.current_episode_titles = titles
        for number, row in self.episode_rows:
            title = titles.get(number)
            if title:
                row.set_subtitle(GLib.markup_escape_text(title))
        for number, _filename, row, _file in getattr(self, 'batch_episode_rows', []):
            title = titles.get(number)
            if title:
                row.set_title(tr(f'Episódio {number:02d} · {title}'))
        if getattr(self, 'episode_filter_query', ''):
            self.filter_episodes()
        if getattr(self, 'active_episode', None) in titles:
            self.results_heading.set_text(self.episode_row_title(self.active_episode))
        return False

    def episode_row_title(self, number):
        title = self.current_episode_titles.get(number)
        return tr(f'Episódio {number:02d} · {title}') if title else tr(f'Episódio {number:02d}')

    @staticmethod
    def anime_meta_text(media, count):
        values = []
        if media.get('format'):
            values.append(media['format'].replace('_', ' ').title())
        if media.get('seasonYear'):
            values.append(str(media['seasonYear']))
        if count:
            values.append(tr(f'{count} episódios'))
        if media.get('averageScore'):
            values.append(f'★ {media["averageScore"] / 10:.1f}')
        return '  ·  '.join(values)

    @staticmethod
    def plain_description(description):
        parser = _PlainText()
        try:
            parser.feed(description)
            return ' '.join(parser.parts).strip() or unescape(description).strip()
        except Exception:
            return unescape(description).strip()

    def load_anime_poster(self, media):
        cover = (media.get('coverImage') or {}).get('large') or (media.get('coverImage') or {}).get('medium')
        if not cover:
            self.anime_poster.set_paintable(None)
            return
        media_id = media.get('id')
        future = IMAGE_POOL.submit(self.cached_cover, media_id, cover)
        future.add_done_callback(lambda result: GLib.idle_add(self.set_anime_poster, result, media_id))

    def set_anime_poster(self, future: Future, media_id):
        if not self.current_anime or self.current_anime.get('id') != media_id:
            return False
        try:
            texture = Gdk.Texture.new_from_filename(str(future.result()))
            self.anime_poster.set_paintable(texture)
        except Exception:
            self.anime_poster.set_paintable(None)
        return False

    def populate_episodes(self, count):
        self.clear_list(self.episode_list)
        self.episode_scroll.get_vadjustment().set_value(0)
        self.episode_rows = []
        self.episode_watched_badges = {}
        self.episode_count = count
        self.watched_episodes = watch_progress.watched_episodes((self.current_anime or {}).get('id'))
        self.episode_filter_query = ''
        self.episode_filtered_numbers = range(1, count + 1)
        self.episode_rendered_count = 0
        self.episode_search.set_visible(bool(count))
        self.episode_content.set_visible_child_name('list' if count else 'empty')
        self.episode_search.set_text('')
        self.load_more_episodes()

    def _connect_scroll_loader(self, scroller, loader):
        if not hasattr(self, '_scroll_loader_pending'):
            self._scroll_loader_pending = set()
        key = id(scroller)
        adjustment = scroller.get_vadjustment()
        callback = lambda *_: self._queue_scroll_loader(scroller, loader, key)
        adjustment.connect('value-changed', callback)
        adjustment.connect('changed', callback)

    def _queue_scroll_loader(self, scroller, loader, key):
        if key in self._scroll_loader_pending:
            return
        if not self._is_near_scroll_end(scroller):
            return
        self._scroll_loader_pending.add(key)
        GLib.idle_add(self._run_scroll_loader, scroller, loader, key)

    @staticmethod
    def _is_near_scroll_end(scroller):
        if not scroller.get_mapped():
            return False
        adjustment = scroller.get_vadjustment()
        if adjustment.get_page_size() <= 0:
            return False
        threshold = max(adjustment.get_page_size() * 0.6, 360)
        return adjustment.get_upper() - (adjustment.get_value() + adjustment.get_page_size()) <= threshold

    def _run_scroll_loader(self, scroller, loader, key):
        self._scroll_loader_pending.discard(key)
        if self._is_near_scroll_end(scroller):
            loader()
        return False

    def load_more_episodes(self):
        start = self.episode_rendered_count
        end = min(start + EPISODE_RENDER_BATCH_SIZE, len(self.episode_filtered_numbers))
        for number in self.episode_filtered_numbers[start:end]:
            row = Adw.ActionRow()
            row.set_use_markup(False)
            row.set_title(self.episode_row_title(number))
            row.set_subtitle(tr('Pesquisar releases no Nyaa'))
            number_badge = Gtk.Label(label=f'{number:02d}')
            number_badge.add_css_class('numeric')
            number_badge.add_css_class('heading')
            number_badge.set_size_request(28, -1)
            row.add_prefix(number_badge)
            search_button = Gtk.Button.new_from_icon_name('system-search-symbolic')
            search_button.add_css_class('flat')
            search_button.set_tooltip_text(tr(f'Pesquisar episódio {number:02d}'))
            search_button.connect('clicked', lambda *_args, episode=number: self.search_episode(episode))
            row.add_suffix(search_button)
            watched_badge = Gtk.Image.new_from_icon_name('emblem-ok-symbolic')
            watched_badge.add_css_class('success')
            watched_badge.set_tooltip_text(tr('Assistido'))
            watched_badge.set_visible(number in getattr(self, 'watched_episodes', set()))
            row.add_suffix(watched_badge)
            row.set_activatable(True)
            row.connect('activated', lambda *_args, episode=number: self.search_episode(episode))
            self.episode_list.append(row)
            self.episode_rows.append((number, row))
            self.episode_watched_badges[number] = watched_badge
        self.episode_rendered_count = end
        return False

    def refresh_watched_episodes(self):
        anime_id = (self.current_anime or {}).get('id')
        watched = watch_progress.watched_episodes(anime_id)
        self.watched_episodes = watched
        for number, badge in getattr(self, 'episode_watched_badges', {}).items():
            badge.set_visible(number in watched)
        for number, badges in getattr(self, 'batch_watched_badges', {}).items():
            for badge in badges:
                badge.set_visible(number in watched)

    def filter_episodes(self, *_args):
        query = self.episode_search.get_text().strip().lower()
        self.episode_filter_query = query
        count = getattr(self, 'episode_count', 0)
        titles = getattr(self, 'current_episode_titles', {})
        self.episode_filtered_numbers = (
            range(1, count + 1) if not query else
            [number for number in range(1, count + 1)
             if query in str(number) or query in f'{number:02d}' or
             query in titles.get(number, '').lower()]
        )
        self.clear_list(self.episode_list)
        self.episode_scroll.get_vadjustment().set_value(0)
        self.episode_rows = []
        self.episode_watched_badges = {}
        self.episode_rendered_count = 0
        self.load_more_episodes()

    def anime_view_changed(self, *_args):
        if (self.anime_tabs.get_visible_child_name() == 'batches' and
                self.current_anime and self.batch_view.get_visible_child_name() == 'catalog'):
            self.show_saved_batches()

    def search_episode(self, number):
        self.search_mode = 'episode'
        self.active_episode = number
        self.active_query = f'{anilist.torrent_query(self.current_anime)} {number:02d}'
        self.results_heading.set_text(self.episode_row_title(number))
        if hasattr(self, 'episode_tab_stack'):
            self.episode_tab_stack.set_visible_child_name('results')
        self.anime_tabs.set_visible_child_name('episodes')
        self.stack.set_visible_child_name('anime')
        self.search_releases(self.active_query, mode='episode', episode=number)

    def toggle_batch_pattern(self):
        visible = not self.batch_search_extra.get_visible()
        self.batch_search_extra.set_visible(visible)

    def search_batches(self, edited=False):
        self.search_mode = 'batch'
        self.active_episode = None
        self.active_query = anilist.torrent_query(self.current_anime)
        self.batch_view.set_visible_child_name('catalog')
        self.clear_batch_rows()
        self.show_notice('Buscando batches no Nyaa…')
        self.batch_results = library.favorite_batches(self.current_anime)
        self.render_batch_rows()
        query = self.batch_search_query.get_text().strip() if edited else self.active_query
        if edited and not query:
            self.show_notice('Digite os termos que deseja pesquisar batches no Nyaa.')
            self.batch_search_query.grab_focus()
            return
        self.batch_search_performed = True
        self.search_releases(query, mode='batch', edited=edited)

    def search_edited_batches(self):
        self.search_batches(edited=bool(self.batch_search_query.get_text().strip()))

    def show_anime(self):
        if hasattr(self, 'episode_tab_stack'):
            self.episode_tab_stack.set_visible_child_name('episodes')
        self.stack.set_visible_child_name('anime')
