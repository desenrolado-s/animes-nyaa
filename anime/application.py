"""GTK application shell and composition of the UI components."""
import sys

import gi
gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gio, GLib, Gtk

from .storage import settings
from .ui.catalog_ui import CatalogUI
from .ui.common import CommonUI
from .ui.detail_ui import DetailUI
from .ui.history_ui import HistoryUI
from .ui.library_ui import LibraryUI
from .ui.results_ui import ResultsUI


class AnimeApp(Adw.Application, CommonUI, CatalogUI, DetailUI, ResultsUI, HistoryUI, LibraryUI):
    def __init__(self, smoke=False):
        Adw.Application.__init__(self, application_id='io.github.desenrolado_s.AnimeNyaa')
        self.smoke = smoke
        self.results = []
        self.current_anime = None
        self.busy = False
        self.catalog_query = ''
        self.catalog_page = 0
        self.catalog_has_next = False
        self.search_mode = 'episode'
        self.active_query = ''

    def do_activate(self):
        if getattr(self, 'window', None):
            self.window.present()
            return
        self.window = Adw.ApplicationWindow(application=self, title='にゃあ')
        self.window.set_default_size(1120, 800)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.query = Gtk.SearchEntry(placeholder_text='Buscar anime', width_chars=24)
        self.query.set_max_width_chars(32)
        self.query.set_search_delay(350)
        self.query.connect('activate', lambda *_: self.search_catalog())
        self.query.connect('search-changed', self.catalog_search_changed)
        header.set_title_widget(self.query)
        settings_button = Gtk.Button.new_from_icon_name('emblem-system-symbolic')
        settings_button.set_tooltip_text('Configurações')
        settings_button.connect('clicked', lambda *_: self.show_settings())
        header.pack_end(settings_button)
        self.sidebar_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT,
            transition_duration=180,
        )
        self.sidebar_toggle = Gtk.ToggleButton()
        self.sidebar_toggle.set_child(Gtk.Image.new_from_icon_name('sidebar-show-symbolic'))
        self.sidebar_toggle.set_active(True)
        self.sidebar_toggle.set_tooltip_text('Mostrar ou ocultar a barra lateral')
        self.sidebar_toggle.connect('toggled', self.toggle_sidebar)
        header.pack_start(self.sidebar_toggle)
        toolbar.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(body, 'set_margin_' + side)(24)
        toolbar.set_content(body)
        self.window.set_content(toolbar)

        workspace = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True, vexpand=True)
        workspace.set_resize_start_child(False)
        workspace.set_resize_end_child(True)
        workspace.set_shrink_start_child(True)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sidebar.add_css_class('sidebar')
        sidebar.set_margin_top(4)
        sidebar.set_margin_bottom(4)
        sidebar.set_margin_start(4)
        sidebar.set_margin_end(4)
        sidebar_title = self.label('NAVEGAÇÃO', 'caption-heading')
        sidebar_title.set_margin_start(8)
        sidebar.append(sidebar_title)
        sidebar.append(self.sidebar_button('view-grid-symbolic', 'Catálogo', self.show_catalog))
        sidebar.append(self.sidebar_button('starred-symbolic', 'Minha lista', self.show_my_list))
        sidebar.append(self.sidebar_button('document-open-recent-symbolic', 'Histórico', self.show_history))
        category_title = self.label('CATEGORIA DOS TORRENTS', 'caption-heading')
        category_title.set_margin_start(8)
        category_title.set_margin_top(18)
        sidebar.append(category_title)
        self.category = Gtk.DropDown(model=Gtk.StringList.new([
            'Todas as categorias', 'Legendados em inglês',
            'Legendados em outros idiomas', 'Sem legendas',
        ]))
        self.category.set_hexpand(True)
        self.category.connect('notify::selected', self.category_changed)
        sidebar.append(self.category)
        self.sidebar_revealer.set_child(sidebar)
        self.sidebar_revealer.set_reveal_child(True)
        workspace.set_start_child(self.sidebar_revealer)

        self.stack = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)
        self.stack.add_named(self.build_catalog_page(), 'catalog')
        self.stack.add_named(self.build_anime_page(), 'anime')
        self.stack.add_named(self.build_results_page(), 'results')
        self.stack.add_named(self.build_my_list_page(), 'my-list')
        self.stack.add_named(self.build_history_page(), 'history')
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True, vexpand=True)
        content.append(self.stack)
        workspace.set_end_child(content)
        workspace.connect('notify::position', self.clamp_sidebar_width)
        workspace.set_position(250)
        self.sidebar_paned = workspace
        self.sidebar_position = 250
        self.sidebar_animating = False
        self.sidebar_animation_source = 0

        self.main_overlay = Gtk.Overlay()
        self.main_overlay.set_child(workspace)
        self.notification_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            transition_duration=160,
            halign=Gtk.Align.END,
            valign=Gtk.Align.START,
        )
        self.notification_revealer.set_margin_top(12)
        self.notification_revealer.set_margin_end(12)
        notice = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        notice.add_css_class('card')
        notice.set_size_request(440, -1)
        notice_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(notice_content, 'set_margin_' + side)(12)
        notice_content.append(Gtk.Image.new_from_icon_name('dialog-information-symbolic'))
        self.notification_label = self.label('')
        self.notification_label.set_max_width_chars(42)
        self.notification_label.set_hexpand(True)
        self.notification_label.set_valign(Gtk.Align.CENTER)
        self.notification_label.set_wrap(True)
        notice_content.append(self.notification_label)
        dismiss = Gtk.Button.new_from_icon_name('window-close-symbolic')
        dismiss.add_css_class('flat')
        dismiss.set_tooltip_text('Fechar aviso')
        dismiss.connect('clicked', lambda *_: self.dismiss_notification())
        notice_content.append(dismiss)
        notice.append(notice_content)
        self.notification_revealer.set_child(notice)
        self.main_overlay.add_overlay(self.notification_revealer)
        self.notification_timeout = 0
        body.append(self.main_overlay)

        self.window.present()
        if self.smoke:
            GLib.timeout_add(300, lambda: (self.quit(), False)[1])
        else:
            self.load_catalog(reset=True)

    def sidebar_button(self, icon, text, callback):
        button = Gtk.Button(has_frame=False, hexpand=True)
        row = Gtk.Box(spacing=10)
        row.set_margin_start(6)
        row.set_margin_end(6)
        row.append(Gtk.Image.new_from_icon_name(icon))
        label = self.label(text)
        label.set_hexpand(True)
        row.append(label)
        button.set_child(row)
        button.set_halign(Gtk.Align.FILL)
        button.connect('clicked', lambda *_args: callback())
        return button

    def show_settings(self):
        window = Adw.PreferencesWindow(transient_for=self.window, modal=True, title='Configurações')
        window.set_default_size(620, 360)
        page = Adw.PreferencesPage(title='Geral', icon_name='preferences-system-symbolic')
        group = Adw.PreferencesGroup(
            title='Downloads temporários',
            description='Escolha onde o WebTorrent armazena os dados enquanto reproduz vídeos.',
        )
        row = Adw.ActionRow(title='Pasta dos vídeos temporários')
        row.set_subtitle(str(settings.temporary_directory()))
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)
        choose = Gtk.Button(label='Escolher pasta')
        choose.connect('clicked', lambda *_: self.choose_temporary_directory(window, row))
        reset = Gtk.Button(label='Usar /tmp')
        reset.connect('clicked', lambda *_: self.reset_temporary_directory(row))
        actions.append(choose)
        actions.append(reset)
        row.add_suffix(actions)
        group.add(row)
        page.add(group)
        window.add(page)
        window.present()

    def choose_temporary_directory(self, parent, row):
        chooser = Gtk.FileChooserNative.new(
            'Escolher pasta para vídeos temporários', parent,
            Gtk.FileChooserAction.SELECT_FOLDER, 'Selecionar', 'Cancelar',
        )
        current = settings.temporary_directory()
        if current.is_dir():
            chooser.set_current_folder(Gio.File.new_for_path(str(current)))
        chooser.connect('response', self.temporary_directory_selected, row)
        self.folder_chooser = chooser
        chooser.show()

    def temporary_directory_selected(self, chooser, response, row):
        if response == Gtk.ResponseType.ACCEPT:
            selected = chooser.get_file()
            path = selected.get_path() if selected else None
            if path:
                try:
                    settings.set_temporary_directory(path)
                    row.set_subtitle(str(settings.temporary_directory()))
                except OSError as error:
                    self.show_notice(f'Não foi possível salvar a pasta: {error}')
        chooser.destroy()
        self.folder_chooser = None

    def reset_temporary_directory(self, row):
        try:
            settings.set_temporary_directory(None)
            row.set_subtitle(str(settings.temporary_directory()))
        except OSError as error:
            self.show_notice(f'Não foi possível restaurar /tmp: {error}')

    def toggle_sidebar(self, button):
        if button.get_active():
            self.animate_sidebar(max(180, min(self.sidebar_position, 320)), reveal=True)
        else:
            position = self.sidebar_paned.get_position()
            if position > 0:
                self.sidebar_position = max(180, min(position, 320))
            self.animate_sidebar(0, reveal=False)

    def animate_sidebar(self, target, reveal):
        if self.sidebar_animation_source:
            GLib.source_remove(self.sidebar_animation_source)
            self.sidebar_animation_source = 0
        if reveal:
            self.sidebar_revealer.set_reveal_child(True)
        start = self.sidebar_paned.get_position()
        started_at = GLib.get_monotonic_time()
        duration = 220_000
        self.sidebar_animating = True

        def step():
            progress = min(1.0, (GLib.get_monotonic_time() - started_at) / duration)
            eased = 1 - (1 - progress) ** 3
            position = round(start + (target - start) * eased)
            self.sidebar_paned.set_position(position)
            if progress < 1:
                return True
            self.sidebar_animation_source = 0
            self.sidebar_animating = False
            if reveal:
                self.sidebar_position = target
            else:
                self.sidebar_revealer.set_reveal_child(False)
            return False

        self.sidebar_animation_source = GLib.timeout_add(16, step)

    def clamp_sidebar_width(self, paned, *_args):
        position = paned.get_position()
        if self.sidebar_animating:
            if position > 320:
                paned.set_position(320)
            return
        if self.sidebar_revealer.get_reveal_child() and position < 180:
            paned.set_position(180)
        elif position > 320:
            paned.set_position(320)
        elif position > 0:
            self.sidebar_position = position


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    Adw.init()
    return AnimeApp(smoke='--smoke-test' in argv).run([argv[0]])
