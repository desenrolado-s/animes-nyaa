"""Shared GTK styling and small widget helpers."""
from concurrent.futures import ThreadPoolExecutor

import gi
gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gtk
from gi.repository import GLib

from .i18n import tr

IMAGE_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix='anime-cover')
CATEGORY_CODES = ('1_0', '1_2', '1_3', '1_4')


class CommonUI:
    def label(self, text, style=''):
        item = Gtk.Label(label=tr(text), xalign=0, wrap=True)
        if style:
            item.add_css_class(style)
        return item

    def button(self, text, callback):
        item = Gtk.Button(label=tr(text))
        item.set_cursor_from_name('pointer')
        item.connect('clicked', lambda *_: callback())
        return item

    def show_notice(self, message):
        self.notification_label.set_text(tr(message))
        self.notification_revealer.set_reveal_child(True)
        if getattr(self, 'notification_timeout', 0):
            GLib.source_remove(self.notification_timeout)
        self.notification_timeout = GLib.timeout_add_seconds(5, self.dismiss_notification)

    def dismiss_notification(self):
        self.notification_revealer.set_reveal_child(False)
        self.notification_timeout = 0
        return False

    @staticmethod
    def clear_list(widget):
        while widget.get_first_child():
            widget.remove(widget.get_first_child())
