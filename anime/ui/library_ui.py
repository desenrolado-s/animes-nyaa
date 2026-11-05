"""Personal anime list and list membership actions."""
import gi
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gdk, GLib, Gtk

from ..services import anilist
from ..storage import library
from .common import IMAGE_POOL


class LibraryUI:
    def build_my_list_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        heading = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        title = self.label('Minha lista', 'title-1')
        title.set_hexpand(True)
        heading.append(title)
        self.my_list_count = self.label('', 'dim-label')
        heading.append(self.my_list_count)
        page.append(heading)
        self.my_list_rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.my_list_rows.add_css_class('boxed-list')
        self.my_list_rows.set_vexpand(True)
        self.my_list_rows.set_placeholder(Adw.StatusPage(
            icon_name='starred-symbolic', title='Sua lista está vazia',
            description='Abra um anime e use “Minha lista” para guardá-lo aqui.',
        ))
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.my_list_rows)
        page.append(scroller)
        return page

    def show_my_list(self):
        self.refresh_my_list()
        self.stack.set_visible_child_name('my-list')
        self.show_notice(f'{len(library.load()["anime"])} animes na sua lista.')

    def refresh_my_list(self):
        self.clear_list(self.my_list_rows)
        entries = library.load()['anime']
        self.my_list_count.set_text(f'{len(entries)} animes')
        for media in entries:
            title = media.get('display_title') or anilist.display_title(media)
            subtitle = '   ·   '.join(value for value in (
                (media.get('format') or '').replace('_', ' ').title(),
                str(media.get('seasonYear') or ''),
                f"{media.get('episodes')} episódios" if media.get('episodes') else '',
            ) if value)
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            cover = Gtk.Picture()
            cover.set_size_request(64, 90)
            cover.set_content_fit(Gtk.ContentFit.COVER)
            cover.set_can_shrink(True)
            cover.set_visible(False)
            poster = Gtk.Overlay()
            poster.set_size_request(64, 90)
            poster.set_child(Gtk.Image.new_from_icon_name('image-x-generic-symbolic'))
            poster.add_overlay(cover)
            row.add_prefix(poster)
            row.add_suffix(self.button('Abrir', lambda selected=media: self.open_anime(selected)))
            row.add_suffix(self.button('Remover', lambda selected=media: self.remove_from_my_list(selected)))
            self.my_list_rows.append(row)
            image = media.get('coverImage') or {}
            cover_url = image.get('large') or image.get('medium') or media.get('cover_url')
            if cover_url and media.get('id') is not None:
                future = IMAGE_POOL.submit(self.cached_cover, media.get('id'), cover_url)
                future.add_done_callback(
                    lambda result, target=cover: GLib.idle_add(self.set_library_cover, target, result)
                )

    @staticmethod
    def set_library_cover(picture, future):
        if not picture.get_parent():
            return False
        try:
            texture = Gdk.Texture.new_from_filename(str(future.result()))
            picture.set_paintable(texture)
            picture.set_visible(True)
        except Exception:
            pass
        return False

    def toggle_current_anime_in_list(self):
        if not self.current_anime:
            return
        is_saved = library.toggle_anime(self.current_anime)
        self.update_my_list_button(is_saved)
        self.show_notice('Anime adicionado à Minha lista.' if is_saved else 'Anime removido da Minha lista.')
        if self.stack.get_visible_child_name() == 'my-list':
            self.refresh_my_list()

    def update_my_list_button(self, is_saved=None):
        if not getattr(self, 'my_list_button', None) or not self.current_anime:
            return
        saved = library.contains_anime(self.current_anime) if is_saved is None else is_saved
        self.my_list_button.set_label('✓ Na minha lista' if saved else '＋ Minha lista')
        self.my_list_button.set_tooltip_text(
            'Remover este anime da Minha lista' if saved else 'Adicionar este anime à Minha lista'
        )
        if saved:
            self.my_list_button.add_css_class('suggested-action')
        else:
            self.my_list_button.remove_css_class('suggested-action')

    def remove_from_my_list(self, media):
        library.remove_anime(media)
        self.refresh_my_list()
        if self.current_anime and library.anime_id(self.current_anime) == library.anime_id(media):
            self.update_my_list_button(False)
