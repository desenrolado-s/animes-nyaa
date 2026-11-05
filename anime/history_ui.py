"""History page with readable release details and playback actions."""
from datetime import datetime

import gi
gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gtk

from . import history


class HistoryUI:
    def build_history_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        heading = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        title = self.label('Histórico', 'title-1')
        title.set_hexpand(True)
        heading.append(title)
        self.history_count = self.label('', 'dim-label')
        heading.append(self.history_count)
        clear_button = self.button('Limpar histórico', self.clear_history)
        clear_button.add_css_class('destructive-action')
        heading.append(clear_button)
        page.append(heading)

        self.history_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.history_list.add_css_class('boxed-list')
        self.history_list.set_vexpand(True)
        self.history_list.set_placeholder(Adw.StatusPage(
            icon_name='document-open-recent-symbolic',
            title='Seu histórico está vazio',
            description='Os animes reproduzidos aparecerão aqui.',
        ))
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.history_list)
        page.append(scroller)
        return page

    def show_history(self):
        self.refresh_history_page()
        self.stack.set_visible_child_name('history')
        self.show_notice(f'{len(history.load())} reproduções no histórico.')

    def refresh_history_page(self):
        self.clear_list(self.history_list)
        rows = history.load()[:100]
        self.history_count.set_text(f'{len(rows)} reproduções')
        for item in rows:
            title = item.get('title') or 'Anime sem título'
            episode = item.get('episode_file') or item.get('release') or 'Release desconhecida'
            released = item.get('release') or ''
            watched = self.history_timestamp(item.get('watched_at', ''))
            details = '   ·   '.join(value for value in (episode, item.get('size', ''), watched) if value)
            row = Adw.ActionRow(title=title, subtitle=details)
            row.add_prefix(Gtk.Image.new_from_icon_name('media-playback-start-symbolic'))
            if released and released != episode:
                row.set_tooltip_text(released)
            row.add_suffix(self.button('Reproduzir', lambda selected=item: self.play_history_item(selected)))
            row.add_suffix(self.button('Remover', lambda selected=item: self.remove_history_item(selected)))
            self.history_list.append(row)

    @staticmethod
    def history_timestamp(value):
        try:
            return datetime.fromisoformat(value).astimezone().strftime('%d/%m/%Y %H:%M')
        except (TypeError, ValueError):
            return value

    def play_history_item(self, item):
        self.play_item(item, use_current_anime=False,
                       file_index=item.get('file_index'), file_name=item.get('episode_file'))

    def remove_history_item(self, item):
        history.remove(item)
        self.refresh_history_page()

    def clear_history(self):
        history.clear()
        self.refresh_history_page()
