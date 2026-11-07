"""Nyaa result lists, batch file browsing and mpv playback."""
import atexit
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import urllib.parse
import webbrowser

import gi
gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, GLib, Gtk

from ..services import anilist, lastfm, nyaa, torrent
from ..storage import history, lastfm_progress, library, settings, watch_progress
from .common import CATEGORY_CODES
from .i18n import tr


BATCH_ROW_RENDER_BATCH_SIZE = 30
BATCH_FILE_RENDER_BATCH_SIZE = 40
ACTIVE_PLAYBACK_DIRECTORIES = set()


class ResultsUI:
    def build_results_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        nav = Gtk.Box(spacing=10)
        nav.append(self.button('← Episódios e batches', self.show_anime))
        self.results_heading = self.label('')
        self.results_heading.add_css_class('title-2')
        nav.append(self.results_heading)
        page.append(nav)

        search_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        search_card.add_css_class('card')
        search_card.set_margin_top(4)
        search_card.set_margin_bottom(4)
        search_card.set_margin_start(4)
        search_card.set_margin_end(4)
        search_label = self.label('Consulta enviada ao Nyaa', 'caption-heading')
        search_card.append(search_label)
        query_row = Gtk.Box(spacing=8)
        self.release_query = Gtk.Entry(placeholder_text=tr('Termos usados na pesquisa'), hexpand=True)
        self.release_query.set_activates_default(True)
        self.release_query.connect('activate', lambda *_: self.search_edited_releases())
        query_row.append(self.release_query)
        query_row.append(self.button('Pesquisar', self.search_edited_releases))
        search_card.append(query_row)
        self.search_trace = self.label('', 'dim-label')
        self.search_trace.set_margin_start(4)
        search_card.append(self.search_trace)

        self.extra_pattern_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.extra_pattern = Gtk.Entry(placeholder_text='E.g. 1080p, [Group], dual audio', hexpand=True)
        self.extra_pattern.set_tooltip_text(tr('Este termo será acrescentado à consulta principal.'))
        self.extra_pattern_revealer.set_child(self.extra_pattern)
        search_card.append(self.extra_pattern_revealer)
        pattern_actions = Gtk.Box(spacing=8)
        self.extra_pattern_button = self.button('＋ Adicionar padrão de pesquisa', self.toggle_extra_pattern)
        self.extra_pattern_button.add_css_class('flat')
        pattern_actions.append(self.extra_pattern_button)
        search_card.append(pattern_actions)
        page.append(search_card)

        self.results_count = self.label('Resultados encontrados', 'heading')
        page.append(self.results_count)
        self.release_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.release_list.add_css_class('boxed-list')
        self.release_list.set_placeholder(Adw.StatusPage(
            icon_name='system-search-symbolic', title=tr('Nenhuma release encontrada'),
            description=tr('Altere os termos da consulta e tente novamente.'),
        ))
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.release_list)
        page.append(scroller)
        actions = Gtk.Box(spacing=10)
        play = self.button('▶  Assistir selecionado', self.play_selected)
        play.add_css_class('suggested-action')
        actions.append(play)
        actions.append(self.button('Busca no Nyaa', self.open_page))
        page.append(actions)
        return page

    def toggle_extra_pattern(self):
        visible = not self.extra_pattern_revealer.get_reveal_child()
        self.extra_pattern_revealer.set_reveal_child(visible)
        self.extra_pattern_button.set_label(tr('− Remover padrão adicional') if visible else tr('＋ Adicionar padrão de pesquisa'))
        if visible:
            self.extra_pattern.grab_focus()

    def search_edited_releases(self):
        query = self.release_query.get_text().strip()
        if not query:
            self.show_notice('Digite os termos que deseja pesquisar no Nyaa.')
            self.release_query.grab_focus()
            return
        self.search_releases(query, mode=self.search_mode,
                             episode=getattr(self, 'active_episode', None), edited=True)

    def clear_release_rows(self):
        self.clear_list(self.release_list)

    def clear_batch_rows(self):
        self.clear_list(self.batch_list)

    def show_saved_batches(self):
        self.batch_results = library.favorite_batches(self.current_anime)
        self.render_batch_rows()
        count = len(self.batch_results)
        self.batch_search_trace.set_text(
            tr(f'{count} batches favoritos salvos. Clique em “Buscar batches” para atualizar.')
            if count else tr('Seus batches favoritos aparecerão aqui, mesmo antes de pesquisar.')
        )
        self.show_notice(tr(f'{count} batches favoritos salvos para este anime.') if count else
                    tr('Você pode buscar batches ou favoritar um para encontrá-lo aqui depois.'))

    def search_releases(self, query, mode='episode', episode=None, edited=False):
        if self.busy:
            return
        self.busy = True
        self.show_notice('Buscando releases no Nyaa…')
        self.clear_release_rows()
        category = CATEGORY_CODES[self.category.get_selected()]
        if mode == 'batch':
            extra_pattern = self.batch_search_extra.get_text().strip() if self.batch_search_extra.get_visible() else ''
        else:
            extra_pattern = self.extra_pattern.get_text().strip() if self.extra_pattern_revealer.get_reveal_child() else ''
        anime_titles = (self.current_anime.get('title') or {}) if self.current_anime else {}
        seasons = [nyaa.season_number_from_title(anime_titles.get(key, ''))
                   for key in ('english', 'romaji', 'native')]
        season = next((value for value in seasons if value is not None), None)
        base_query_sets = [[query]] if edited else self.default_query_sets(mode, episode)
        query_sets = [[f'{term} {extra_pattern}'.strip() for term in terms] for terms in base_query_sets]
        display_queries = list(dict.fromkeys(term for terms in query_sets for term in terms))
        editable_query = query if edited else (base_query_sets[0][0] if base_query_sets and base_query_sets[0] else query)
        if mode == 'batch':
            self.batch_search_query.set_text(editable_query)
            self.batch_search_trace.set_text(tr('Consultas: ') + '  ·  '.join(display_queries))
        else:
            self.release_query.set_text(editable_query)
            self.search_trace.set_text(tr('Consultas: ') + '  ·  '.join(display_queries))
        self.active_search_query = display_queries[0] if display_queries else query

        def worker():
            try:
                rows = []
                searched = []
                for queries in query_sets:
                    seen = set()
                    for search_query in queries:
                        searched.append(search_query)
                        for result in nyaa.search(search_query, category):
                            batch = nyaa.is_batch_title(result['title'])
                            if mode == 'batch' and not batch:
                                continue
                            if mode == 'episode' and (batch or (not edited and not nyaa.matches_episode(
                                    result['title'], episode, season=season))):
                                continue
                            result['is_batch'] = batch
                            if result['magnet'] not in seen:
                                seen.add(result['magnet'])
                                rows.append(result)
                    if rows:
                        break
                error = None
            except Exception as exc:
                rows, error, searched = [], exc, []
            callback = self.finish_batches if mode == 'batch' else self.finish_releases
            GLib.idle_add(callback, rows, error, query, searched)

        threading.Thread(target=worker, daemon=True).start()

    def default_query_sets(self, mode, episode):
        titles = self.current_anime.get('title') if self.current_anime else {}
        anime_titles = list(dict.fromkeys(titles.get(key, '') for key in ('english', 'romaji', 'native')))
        anime_titles = [title for title in anime_titles if title]
        if not anime_titles:
            anime_titles = [self.active_query]
        if mode == 'batch':
            return [[f'{title} {term}' for term in ('batch', 'complete', 'season')]
                    for title in anime_titles]
        seasons = [nyaa.season_number_from_title(title) for title in anime_titles]
        season = next((value for value in seasons if value is not None), None)
        search_titles = []
        for title in anime_titles:
            without_season = nyaa.strip_season_from_title(title)
            if without_season:
                search_titles.append(without_season)
            if without_season != title:
                search_titles.append(title)
        anime_titles = list(dict.fromkeys(search_titles))
        number = int(episode)
        padded = f'{number:02d}'
        patterns = []
        if season is not None:
            season_padded = f'{season:02d}'
            patterns.extend((
                f'S{season_padded}E{padded}',
                f'S{season}E{padded}',
                f'S{season_padded}E{number}',
                f'E{padded}S{season_padded}',
                f'E0{number}S0{season}',
            ))
        patterns.extend((
            f'E{padded}',
            f'EP{padded}',
            f'EP {padded}',
            f'Episode {padded}',
            padded,
            str(number),
        ))
        if number < 100:
            three_digits = f'{number:03d}'
            patterns.extend((f'E{three_digits}', f'EP{three_digits}', three_digits))
        patterns = list(dict.fromkeys(patterns))
        return [[f'{title} {pattern}' for pattern in patterns] for title in anime_titles]

    def category_changed(self, *_args):
        if not getattr(self, 'current_anime', None):
            return
        if self.stack.get_visible_child_name() == 'results' and getattr(self, 'active_episode', None):
            if self.release_query.get_text().strip():
                self.search_edited_releases()
            else:
                self.search_episode(self.active_episode)
        elif self.stack.get_visible_child_name() == 'anime' and self.anime_tabs.get_visible_child_name() == 'batches':
            if getattr(self, 'batch_search_performed', False):
                self.search_edited_batches()
            else:
                self.show_saved_batches()

    def finish_batches(self, rows, error, query='', searched=None):
        self.busy = False
        if error:
            self.show_notice(tr(f'Falha ao consultar batches no Nyaa: {error}'))
            return False
        favorites = library.favorite_batches(self.current_anime)
        seen = {item.get('magnet') for item in favorites}
        merged = favorites + [item for item in rows if item.get('magnet') not in seen]
        self.batch_results = self.sort_batches_by_favorite(merged)
        if searched is not None:
            self.batch_search_trace.set_text(tr('Consultas: ') + '  ·  '.join(searched))
        self.render_batch_rows()
        saved_count = len(favorites)
        if rows:
            self.show_notice(tr(f'{len(rows)} batches encontrados; {saved_count} favoritos mantidos no topo.') if saved_count
                        else tr(f'{len(rows)} batches encontrados.'))
        else:
            self.show_notice(tr(f'Nenhum batch novo encontrado; {saved_count} favoritos continuam disponíveis.')
                        if saved_count else tr('Nenhum batch encontrado. Tente outra categoria.'))
        return False

    def sort_batches_by_favorite(self, rows):
        return sorted(rows, key=lambda item: not library.is_favorite_batch(self.current_anime, item))

    def render_batch_rows(self):
        self.clear_batch_rows()
        self.batch_scroll.get_vadjustment().set_value(0)
        self.batch_rows_rendered = 0
        self.load_more_batch_rows()

    def load_more_batch_rows(self):
        start = getattr(self, 'batch_rows_rendered', 0)
        end = min(start + BATCH_ROW_RENDER_BATCH_SIZE, len(self.batch_results))
        for item in self.batch_results[start:end]:
            item['is_batch'] = True
            row = Adw.ActionRow(
                title=item['title'] or tr('Batch sem título'),
                subtitle=f"{item['size']}   ·   ↑ {item['seeders']}   ·   ↓ {item['leechers']}   ·   {item['downloads']} downloads",
            )
            row.add_prefix(Gtk.Image.new_from_icon_name('folder-videos-symbolic'))
            favorite = library.is_favorite_batch(self.current_anime, item)
            favorite_button = Gtk.Button.new_from_icon_name('starred-symbolic' if favorite else 'non-starred-symbolic')
            favorite_button.add_css_class('flat')
            favorite_button.set_tooltip_text(tr('Remover dos batches favoritos') if favorite else tr('Favoritar batch'))
            favorite_button.connect('clicked', lambda *_args, selected=item: self.toggle_batch_favorite(selected))
            row.add_suffix(favorite_button)
            row.add_suffix(self.button('Ver episódios', lambda selected=item: self.load_batch_episodes(selected)))
            self.batch_list.append(row)
        self.batch_rows_rendered = end
        return False

    def toggle_batch_favorite(self, item):
        library.toggle_favorite_batch(self.current_anime, item)
        self.batch_results = self.sort_batches_by_favorite(self.batch_results)
        self.render_batch_rows()

    def finish_releases(self, rows, error, query='', searched=None):
        self.busy = False
        if error:
            self.show_notice(tr(f'Falha ao consultar Nyaa: {error}'))
            return False
        self.results = rows
        if searched is not None:
            self.search_trace.set_text(tr('Consultas: ') + '  ·  '.join(searched))
        self.results_count.set_text(tr(f'{len(rows)} releases encontradas'))
        for item in rows:
            title = item['title'] or tr('Release sem título')
            meta = f"{item['size']}   ·   {item['downloads']} downloads"
            row = Adw.ActionRow(title=title, subtitle=meta)
            seeders = Gtk.Label(label=f"↑ {item['seeders']}")
            seeders.add_css_class('success')
            seeders.add_css_class('numeric')
            row.add_prefix(Gtk.Image.new_from_icon_name('package-x-generic-symbolic'))
            row.add_suffix(seeders)
            leechers = Gtk.Label(label=f"↓ {item['leechers']}")
            leechers.add_css_class('dim-label')
            row.add_suffix(leechers)
            play = Gtk.Button.new_from_icon_name('media-playback-start-symbolic')
            play.add_css_class('suggested-action')
            play.set_tooltip_text(tr('Reproduzir esta release'))
            play.connect('clicked', lambda *_args, selected=item: self.play_item(selected))
            row.add_suffix(play)
            list_row = Gtk.ListBoxRow(child=row)
            list_row.set_activatable(True)
            list_row.connect('activate', lambda selected: self.release_list.select_row(selected))
            self.release_list.append(list_row)
        if rows:
            self.show_notice(tr(f'{len(rows)} releases encontradas para o episódio {self.active_episode:02d}.'))
        elif self.active_episode:
            self.show_notice(tr(f'Nenhuma release individual encontrada para o episódio {self.active_episode:02d}. Confira a aba Batches.'))
        else:
            self.show_notice('Nenhum torrent encontrado para esta busca.')
        return False

    def play_selected(self):
        selected = self.release_list.get_selected_row()
        if selected is None or selected.get_index() >= len(self.results):
            self.show_notice('Selecione uma release primeiro.')
            return
        self.play_item(self.results[selected.get_index()])

    def load_batch_episodes(self, item):
        self.selected_batch = item
        self.batch_load_request = getattr(self, 'batch_load_request', 0) + 1
        request_id = self.batch_load_request
        self.show_notice('Lendo episódios do batch…')

        def worker():
            try:
                files, error = torrent.list_video_files(item['magnet']), None
            except Exception as exc:
                files, error = [], exc
            GLib.idle_add(self.finish_batch_episodes, files, error, item, request_id)

        threading.Thread(target=worker, daemon=True).start()

    def finish_batch_episodes(self, files, error, item, request_id=None):
        if request_id is not None and request_id != getattr(self, 'batch_load_request', request_id):
            return False
        if error:
            self.show_notice(str(error))
            return False
        self.selected_batch = item
        self.batch_episode_heading.set_text(item.get('title', tr('Episódios do batch')))
        self.clear_list(self.batch_episode_list)
        self.batch_episode_rows = []
        self.batch_watched_badges = {}
        self.batch_episode_files = []
        for position, file in enumerate(files, start=1):
            number = torrent.episode_number(file['name']) or position
            self.batch_episode_files.append((number, file['name'].lower(), file))
        self.batch_episode_filter_query = ''
        self.batch_filtered_files = list(self.batch_episode_files)
        self.batch_files_rendered = 0
        self.batch_episode_scroll.get_vadjustment().set_value(0)
        self.load_more_batch_episodes()
        self.batch_episode_count.set_text(tr(f'{len(files)} episódios'))
        self.batch_episode_search.set_text('')
        self.batch_view.set_visible_child_name('episodes')
        self.refresh_watched_episodes()
        self.show_notice(tr(f'{len(files)} episódios encontrados dentro do batch.'))
        return False

    def filter_batch_episodes(self, *_args):
        query = self.batch_episode_search.get_text().strip().lower()
        self.batch_episode_filter_query = query
        source_files = getattr(self, 'batch_episode_files', [])
        self.batch_filtered_files = [record for record in source_files
                                     if not query or query in str(record[0]) or
                                     f'{record[0]:02d}' in query or query in record[1]]
        self.clear_list(self.batch_episode_list)
        self.batch_episode_scroll.get_vadjustment().set_value(0)
        self.batch_episode_rows = []
        self.batch_watched_badges = {}
        self.batch_files_rendered = 0
        self.batch_episode_count.set_text(tr(f'{len(self.batch_filtered_files)} episódios'))
        self.load_more_batch_episodes()

    def load_more_batch_episodes(self):
        start = getattr(self, 'batch_files_rendered', 0)
        end = min(start + BATCH_FILE_RENDER_BATCH_SIZE, len(self.batch_filtered_files))
        watched = getattr(self, 'watched_episodes', set())
        for number, filename, file in self.batch_filtered_files[start:end]:
            row = Adw.ActionRow(title=self.episode_row_title(number),
                                subtitle=f"{file['name']}  ·  {file['size']}")
            badge = Gtk.Label(label=f'{number:02d}')
            badge.add_css_class('numeric')
            badge.add_css_class('dim-label')
            row.add_prefix(badge)
            play = Gtk.Button.new_from_icon_name('media-playback-start-symbolic')
            play.add_css_class('flat')
            play.set_tooltip_text(tr(f'Assistir episódio {number:02d}'))
            play.connect('clicked', lambda *_args, selected=file: self.play_batch_episode(selected))
            row.add_suffix(play)
            watched_badge = Gtk.Label(label='✓')
            watched_badge.add_css_class('success')
            watched_badge.set_tooltip_text(tr('Assistido'))
            watched_badge.set_visible(number in watched)
            row.add_suffix(watched_badge)
            row.set_activatable(True)
            row.connect('activated', lambda *_args, selected=file: self.play_batch_episode(selected))
            self.batch_episode_list.append(row)
            self.batch_episode_rows.append((number, filename, row, file))
            self.batch_watched_badges.setdefault(number, []).append(watched_badge)
        self.batch_files_rendered = end
        return False

    def play_batch_episode(self, file):
        if getattr(self, 'selected_batch', None):
            self.play_item(self.selected_batch, file_index=file['index'], file_name=file['name'])

    def play_item(self, item, use_current_anime=True, file_index=None, file_name=None,
                  episode_number=None):
        webtorrent = shutil.which('webtorrent')
        node = shutil.which('node')
        mpv = shutil.which('mpv')
        if not mpv:
            self.show_notice('Instale o mpv para reproduzir torrents.')
            return
        if not webtorrent or not node:
            self.show_notice('Node.js e WebTorrent CLI não foram encontrados. Reinstale o aplicativo.')
            return
        playback_directory = None
        try:
            temporary_directory = settings.temporary_directory()
            temporary_directory.mkdir(parents=True, exist_ok=True)
            playback_directory = Path(tempfile.mkdtemp(prefix='anime-nyaa-', dir=temporary_directory))
            ACTIVE_PLAYBACK_DIRECTORIES.add(playback_directory)
            helper = Path(__file__).resolve().parents[1] / 'services' / 'stream_episode.mjs'
            command = [node, str(helper), webtorrent, item['magnet'],
                       str(file_index) if file_index is not None else '-1',
                       str(playback_directory), mpv]
            child_environment = os.environ.copy()
            # PyInstaller prepends its private libraries for Python and GTK.
            # External Node/npm native modules and the host mpv must use the
            # distro libraries instead of incompatible bundled OpenSSL/libffi.
            original_library_path = child_environment.pop('LD_LIBRARY_PATH_ORIG', None)
            if original_library_path:
                child_environment['LD_LIBRARY_PATH'] = original_library_path
            else:
                child_environment.pop('LD_LIBRARY_PATH', None)
            process = subprocess.Popen(
                command, cwd=str(Path.home()), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                env=child_environment,
                start_new_session=True,
            )
            try:
                (playback_directory / 'session.pid').write_text(str(process.pid), encoding='ascii')
            except OSError:
                pass
        except (OSError, KeyError, ValueError) as exc:
            if playback_directory is not None:
                ACTIVE_PLAYBACK_DIRECTORIES.discard(playback_directory)
                shutil.rmtree(playback_directory, ignore_errors=True)
            self.show_notice(tr(f'Não foi possível iniciar a reprodução: {exc}'))
            return
        if episode_number is None:
            episode_number = item.get('episode_number')
        if episode_number is None and file_name:
            episode_number = torrent.episode_number(file_name)
        if episode_number is None and use_current_anime:
            episode_number = getattr(self, 'active_episode', None)
        anime = self.current_anime if use_current_anime else None
        anime_id = (anime or {}).get('id') or item.get('anilist_id')
        try:
            watch_progress.mark_watched(anime_id, episode_number)
        except Exception as exc:
            self.show_notice(tr(f'A reprodução iniciou, mas não foi possível salvar o progresso: {exc}'))
        try:
            history.record(item, anime, file_index=file_index, file_name=file_name,
                           episode_number=episode_number)
        except Exception as exc:
            self.show_notice(tr(f'A reprodução iniciou, mas não foi possível salvar no histórico: {exc}'))
        if anime_id and (self.current_anime or {}).get('id') == anime_id:
            self.refresh_watched_episodes()
        credentials = settings.lastfm_credentials()
        if (credentials['enabled'] and credentials['session_key']
                and lastfm_progress.claim(anime_id, episode_number)):
            anime_title = (anime or {}).get('display_title') or item.get('title', 'Anime')
            threading.Thread(
                target=self.scrobble_episode_themes,
                args=(anime_id, episode_number, anime_title, credentials, int(time.time())), daemon=True,
            ).start()
        threading.Thread(
            target=self.monitor_playback,
            args=(process, file_name or item['title'], playback_directory), daemon=True,
        ).start()
        self.show_notice(tr(f'Abrindo no mpv: {file_name or item["title"]}'))

    def scrobble_episode_themes(self, anime_id, episode_number, anime_title, credentials, timestamp):
        try:
            tracks = lastfm.episode_tracks(anime_id, episode_number)
            if not tracks:
                lastfm_progress.release(anime_id, episode_number)
                GLib.idle_add(self.show_notice,
                              tr(f'Não encontrei abertura e encerramento para {anime_title}.'))
                return
            accepted = lastfm.scrobble(
                credentials['api_key'], credentials['api_secret'],
                credentials['session_key'], tracks, timestamp=timestamp,
            )
            lastfm_progress.mark_submitted(anime_id, episode_number)
            GLib.idle_add(self.show_notice,
                          tr(f'{accepted} tema(s) de {anime_title} enviados ao Last.fm.'))
        except Exception as exc:
            lastfm_progress.release(anime_id, episode_number)
            GLib.idle_add(self.show_notice, tr(f'Falha ao enviar os temas ao Last.fm: {exc}'))

    def monitor_playback(self, process, title, playback_directory=None):
        try:
            output, _ = process.communicate()
            if process.returncode:
                details = (output or '').strip().splitlines()
                reason = '\n'.join(details[-4:])[-500:] if details else tr(f'WebTorrent encerrou com código {process.returncode}.')
                GLib.idle_add(self.show_notice, tr(f'Falha ao reproduzir {title}: {reason}'))
        finally:
            if playback_directory is not None:
                ACTIVE_PLAYBACK_DIRECTORIES.discard(playback_directory)
                shutil.rmtree(playback_directory, ignore_errors=True)

    def open_page(self):
        query = getattr(self, 'active_search_query', '') or self.release_query.get_text().strip()
        if not query:
            query = self.active_query or anilist.torrent_query(self.current_anime or {})
            if self.search_mode == 'batch':
                query = f'{query} batch'
        category = CATEGORY_CODES[self.category.get_selected()]
        url = 'https://nyaa.si/?' + urllib.parse.urlencode({'f': '0', 'c': category, 'q': query})
        webbrowser.open(url)
