"""AniList catalogue page and asynchronous cover loading."""
import threading
from pathlib import Path
from urllib.request import Request, urlopen

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Pango', '1.0')
from gi.repository import Gdk, GLib, Gtk, Pango

from ..services import anilist
from .common import IMAGE_POOL
from .i18n import tr


class CatalogUI:
    def catalog_search_changed(self, *_args):
        if self.stack.get_visible_child_name() == 'catalog':
            self.search_catalog()

    def show_catalog(self):
        self.stack.set_visible_child_name('catalog')
        self.show_notice('Escolha um anime do catálogo para pesquisar releases no Nyaa.')

    def build_catalog_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.catalog_heading = self.label('Em alta no AniList')
        page.append(self.catalog_heading)
        self.catalog_grid = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            min_children_per_line=2,
            max_children_per_line=7,
            row_spacing=12,
            column_spacing=10,
            homogeneous=True,
            vexpand=True,
        )
        self.catalog_grid.set_activate_on_single_click(True)
        # Keep the last row clear of the floating pagination button.
        self.catalog_grid.set_margin_bottom(64)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.catalog_grid)

        overlay = Gtk.Overlay()
        overlay.set_child(scroller)
        self.more_button = self.button('Carregar mais', self.load_more)
        self.more_button.set_size_request(150, -1)
        self.more_button.set_halign(Gtk.Align.CENTER)
        self.more_button.set_valign(Gtk.Align.END)
        self.more_button.set_margin_bottom(15)
        self.more_button.add_css_class('suggested-action')
        self.more_button.set_visible(False)
        overlay.add_overlay(self.more_button)

        self.more_loading = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.END)
        self.more_loading.set_margin_bottom(15)
        self.more_loading.set_size_request(48, 48)
        self.more_loading.add_css_class('card')
        self.more_spinner = Gtk.Spinner(width_request=24, height_request=24,
                                        halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.more_loading.append(self.more_spinner)
        self.more_loading.set_visible(False)
        overlay.add_overlay(self.more_loading)
        page.append(overlay)
        return page

    def search_catalog(self):
        self.stack.set_visible_child_name('catalog')
        query = self.query.get_text().strip()
        if not query:
            self.catalog_query = ''
            self.load_catalog(reset=True)
            return
        if self.busy:
            return
        self.catalog_query = query
        self.catalog_page = 0
        self.load_catalog(reset=True)

    def load_catalog(self, reset=False):
        if self.busy:
            return
        self.busy = True
        if reset:
            self.more_button.set_visible(False)
            self.more_loading.set_visible(False)
            self.catalog_page = 0
            self.clear_list(self.catalog_grid)
            self.show_notice('Buscando no AniList…')
        else:
            self.more_button.set_visible(False)
            self.more_loading.set_visible(True)
            self.more_spinner.start()
        page = self.catalog_page + 1
        query = self.catalog_query

        def worker():
            try:
                rows, info = anilist.search(query, page) if query else anilist.trending(page)
                error = None
            except Exception as exc:
                rows, info, error = [], {}, exc
            GLib.idle_add(self.finish_catalog, rows, info, error, query, page, reset)

        threading.Thread(target=worker, daemon=True).start()

    def load_more(self):
        if self.catalog_has_next:
            self.load_catalog()

    def finish_catalog(self, rows, info, error, query, page, reset):
        self.busy = False
        self.more_spinner.stop()
        self.more_loading.set_visible(False)
        if error:
            self.more_button.set_visible(self.catalog_has_next and not reset)
            self.show_notice(tr(f'Falha ao consultar AniList: {error}'))
            return False
        self.catalog_page = page
        self.catalog_has_next = bool(info.get('hasNextPage'))
        self.more_button.set_visible(self.catalog_has_next)
        if reset and not query:
            self.catalog_heading.set_text(tr('Em alta no AniList'))
        elif reset:
            self.catalog_heading.set_text(tr(f'Resultados para “{query}”'))
        for media in rows:
            self.add_media_card(media)
        self.show_notice(tr(f'{len(rows)} animes encontrados no AniList.') if rows else 'Nenhum anime encontrado no AniList.')
        return False

    def add_media_card(self, media):
        title = anilist.display_title(media)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        card.add_css_class('card')
        placeholder = self.label('Capa indisponível', 'muted')
        placeholder.set_size_request(96, 140)
        placeholder.set_halign(Gtk.Align.CENTER)
        placeholder.set_justify(Gtk.Justification.CENTER)
        card.append(placeholder)
        title_label = self.label(title, 'heading')
        title_label.set_max_width_chars(17)
        title_label.set_lines(2)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        title_label.set_justify(Gtk.Justification.CENTER)
        title_label.set_xalign(0.5)
        card.append(title_label)
        details = [media.get('format') or 'Anime']
        if media.get('seasonYear'):
            details.append(str(media['seasonYear']))
        detail_label = self.label(' · '.join(details), 'muted')
        detail_label.set_justify(Gtk.Justification.CENTER)
        detail_label.set_xalign(0.5)
        card.append(detail_label)
        choice = Gtk.Button(child=card)
        choice.set_size_request(138, 202)
        choice.add_css_class('flat')
        choice.set_has_frame(False)
        choice.set_tooltip_text(title)
        choice.connect('clicked', lambda *_args, item=media: self.open_anime(item))
        self.catalog_grid.append(choice)

        cover = (media.get('coverImage') or {}).get('large') or (media.get('coverImage') or {}).get('medium')
        if cover:
            future = IMAGE_POOL.submit(self.cached_cover, media.get('id'), cover)
            future.add_done_callback(lambda result, target=placeholder: GLib.idle_add(self.set_cover, target, result))

    @staticmethod
    def cached_cover(media_id, url):
        cache = Path.home() / '.cache' / 'anime-nyaa' / 'covers'
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / f'{media_id}.img'
        if not path.is_file():
            request = Request(url, headers={'User-Agent': 'AnimeNyaa/1.0'})
            with urlopen(request, timeout=15) as response:
                data = response.read(3_000_000)
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(data)
            temporary.replace(path)
        return path

    @staticmethod
    def set_cover(placeholder, future):
        try:
            path = future.result()
            texture = Gdk.Texture.new_from_filename(str(path))
            picture = Gtk.Picture.new_for_paintable(texture)
            picture.set_size_request(96, 140)
            picture.set_content_fit(Gtk.ContentFit.COVER)
            picture.set_can_shrink(True)
            picture.set_halign(Gtk.Align.CENTER)
            parent = placeholder.get_parent()
            if parent:
                parent.insert_child_after(picture, None)
                parent.remove(placeholder)
        except Exception:
            pass
        return False
