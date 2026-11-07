"""GTK application shell and composition of the UI components."""
import os
import sys
import threading
import webbrowser

import gi
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .services import lastfm
from .storage import settings
from .ui.i18n import tr
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
        self.smoke_error = None
        self.results = []
        self.current_anime = None
        self.busy = False
        self.catalog_query = ''
        self.catalog_page = 0
        self.catalog_has_next = False
        self.search_mode = 'episode'
        self.active_query = ''

    def _configure_bundled_icon_fallback(self, display):
        bundle = getattr(sys, '_MEIPASS', None)
        if not bundle:
            return
        icon_directory = os.path.join(bundle, 'share', 'icons')
        if not os.path.isfile(os.path.join(icon_directory, 'hicolor', 'index.theme')):
            return

        # Add the fallback theme directly: GTK may initialize its icon search
        # path before the PyInstaller runtime hook's XDG_DATA_DIRS change takes effect.
        icon_theme = Gtk.IconTheme.get_for_display(display)
        search_path = icon_theme.get_search_path() or []
        if icon_directory not in search_path:
            icon_theme.set_search_path([icon_directory, *search_path])

    def _bundled_icon_smoke_error(self):
        bundle = getattr(sys, '_MEIPASS', None)
        if not bundle:
            return None

        icon_directory = os.path.join(bundle, 'share', 'icons')
        theme = Gtk.IconTheme.new()
        icon_names = (
            'starred-symbolic',
            'view-grid-symbolic',
            'document-open-recent-symbolic',
            'anime-nyaa',
            'io.github.desenrolado_s.AnimeNyaa',
        )
        missing = []
        bundled_root = os.path.realpath(icon_directory) + os.sep
        theme.set_search_path([icon_directory])
        theme.set_theme_name('anime-nyaa-smoke-missing-theme')
        for icon_name in icon_names:
            paintable = theme.lookup_icon(
                icon_name, [], 16, 1, Gtk.TextDirection.NONE,
                Gtk.IconLookupFlags.FORCE_REGULAR,
            )
            icon_file = paintable.get_file()
            icon_path = os.path.realpath(icon_file.get_path()) if icon_file else ''
            if not icon_path.startswith(bundled_root):
                missing.append(icon_name)
        return ', '.join(missing) if missing else None

    def do_activate(self):
        if getattr(self, 'window', None):
            self.window.present()
            return
        display = Gdk.Display.get_default()
        if display is not None:
            self._configure_bundled_icon_fallback(display)
            if self.smoke:
                self.smoke_error = self._bundled_icon_smoke_error()
                if self.smoke_error:
                    GLib.idle_add(self.quit)
                    return
        self.window = Adw.ApplicationWindow(application=self, title='にゃあ')
        self.window.set_default_size(1120, 800)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.query = Gtk.SearchEntry(placeholder_text=tr('Buscar anime'), width_chars=24)
        self.query.set_max_width_chars(32)
        self.query.set_search_delay(350)
        self.query.connect('activate', lambda *_: self.search_catalog())
        self.query.connect('search-changed', self.catalog_search_changed)
        header.set_title_widget(self.query)
        settings_button = Gtk.Button.new_from_icon_name('emblem-system-symbolic')
        settings_button.set_tooltip_text(tr('Configurações'))
        settings_button.connect('clicked', lambda *_: self.show_settings())
        header.pack_end(settings_button)
        self.sidebar_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT,
            transition_duration=180,
        )
        self.sidebar_toggle = Gtk.ToggleButton()
        self.sidebar_toggle.set_child(Gtk.Image.new_from_icon_name('sidebar-show-symbolic'))
        self.sidebar_toggle.set_active(True)
        self.sidebar_toggle.set_tooltip_text(tr('Mostrar ou ocultar a barra lateral'))
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
            tr('Todas as categorias'), tr('Legendados em inglês'),
            tr('Legendados em outros idiomas'), tr('Sem legendas'),
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
        self.sidebar_position = 250
        self.sidebar_animating = False
        self.sidebar_animation_source = 0
        workspace.connect('notify::position', self.clamp_sidebar_width)
        workspace.set_position(250)
        self.sidebar_paned = workspace

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
        dismiss.set_tooltip_text(tr('Fechar aviso'))
        dismiss.connect('clicked', lambda *_: self.dismiss_notification())
        notice_content.append(dismiss)
        notice.append(notice_content)
        self.notification_revealer.set_child(notice)
        self.main_overlay.add_overlay(self.notification_revealer)
        self.notification_timeout = 0
        body.append(self.main_overlay)

        self.window.present()
        if not self.smoke:
            threading.Thread(target=settings.cleanup_temporary_directory, daemon=True).start()
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
        window = Adw.PreferencesWindow(transient_for=self.window, modal=True, title=tr('Configurações'))
        window.set_default_size(700, 620)
        page = Adw.PreferencesPage(title=tr('Geral'), icon_name='preferences-system-symbolic')
        language_group = Adw.PreferencesGroup(title=tr('Idioma'))
        language_row = Adw.ActionRow(title=tr('Idioma do aplicativo'),
                                     subtitle=tr('A interface é atualizada imediatamente.'))
        self.language_dropdown = Gtk.DropDown(
            model=Gtk.StringList.new([tr('English'), tr('Português')]),
            selected=0 if settings.language() == 'en' else 1,
            valign=Gtk.Align.CENTER,
        )
        self.language_dropdown.connect('notify::selected', self.language_changed)
        language_row.add_suffix(self.language_dropdown)
        language_group.add(language_row)
        page.add(language_group)
        group = Adw.PreferencesGroup(
            title=tr('Downloads temporários'),
            description=tr('Escolha onde o WebTorrent armazena os dados enquanto reproduz vídeos.'),
        )
        row = Adw.ActionRow(title=tr('Pasta dos vídeos temporários'))
        row.set_subtitle(str(settings.temporary_directory()))
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)
        choose = Gtk.Button(label=tr('Escolher pasta'))
        choose.connect('clicked', lambda *_: self.choose_temporary_directory(window, row))
        reset = Gtk.Button(label=tr('Usar /tmp'))
        reset.connect('clicked', lambda *_: self.reset_temporary_directory(row))
        actions.append(choose)
        actions.append(reset)
        row.add_suffix(actions)
        group.add(row)
        page.add(group)

        lastfm_group = Adw.PreferencesGroup(
            title='Last.fm',
            description=tr('Envie a abertura e o encerramento de cada episódio na primeira reprodução.'),
        )
        credentials = settings.lastfm_credentials()
        self.lastfm_api_key_entry = Gtk.Entry(placeholder_text=tr('Chave de API do Last.fm'),
                                               text=credentials['api_key'], hexpand=True)
        api_key_row = Adw.ActionRow(title=tr('Chave de API'))
        api_key_row.add_suffix(self.lastfm_api_key_entry)
        lastfm_group.add(api_key_row)
        self.lastfm_api_secret_entry = Gtk.PasswordEntry(placeholder_text=tr('Segredo da API'), hexpand=True)
        self.lastfm_api_secret_entry.set_text(credentials['api_secret'])
        self.lastfm_api_secret_entry.set_show_peek_icon(True)
        secret_row = Adw.ActionRow(title=tr('Segredo da API'))
        secret_row.add_suffix(self.lastfm_api_secret_entry)
        lastfm_group.add(secret_row)

        self.lastfm_enabled_switch = Gtk.Switch(active=credentials['enabled'], valign=Gtk.Align.CENTER)
        self.lastfm_enabled_switch.connect('notify::active', self.lastfm_enabled_changed)
        enabled_row = Adw.ActionRow(title=tr('Enviar temas ao Last.fm'),
                                    subtitle=tr('Cada episódio é enviado uma única vez.'))
        enabled_row.add_suffix(self.lastfm_enabled_switch)
        enabled_row.set_activatable_widget(self.lastfm_enabled_switch)
        lastfm_group.add(enabled_row)

        actions_row = Adw.ActionRow(title=tr('Conectar conta'))
        self.lastfm_status = Gtk.Label(xalign=1, wrap=True,
                                      label=self.lastfm_status_text(credentials))
        self.lastfm_status.set_max_width_chars(30)
        actions_row.add_suffix(self.lastfm_status)
        self.lastfm_connect_button = Gtk.Button(label=tr('Autorizar'))
        self.lastfm_connect_button.connect('clicked', self.start_lastfm_authorization)
        actions_row.add_suffix(self.lastfm_connect_button)
        self.lastfm_finish_button = Gtk.Button(label=tr('Concluir conexão'))
        self.lastfm_finish_button.set_visible(bool(credentials['pending_token']))
        self.lastfm_finish_button.connect('clicked', self.finish_lastfm_authorization)
        actions_row.add_suffix(self.lastfm_finish_button)
        lastfm_group.add(actions_row)

        info_row = Adw.ActionRow(title=tr('Credenciais do aplicativo'),
                                 subtitle=tr('Crie uma chave em last.fm/api/account/create. Os dados ficam neste computador.'))
        api_link = Gtk.LinkButton(uri='https://www.last.fm/api/account/create', label=tr('Obter chave'))
        info_row.add_suffix(api_link)
        lastfm_group.add(info_row)
        page.add(lastfm_group)
        window.add(page)
        self.settings_window = window
        window.present()

    def language_changed(self, dropdown, _pspec):
        selected_language = 'en' if dropdown.get_selected() == 0 else 'pt'
        if selected_language == settings.language():
            return
        settings.set_language(selected_language)
        active_page = self.stack.get_visible_child_name()
        current_anime = self.current_anime
        settings_window = getattr(self, 'settings_window', None)
        if settings_window:
            settings_window.close()
        self.window.close()
        self.window = None
        self.do_activate()

        def restore_page():
            if current_anime:
                self.open_anime(current_anime)
            elif active_page == 'my-list':
                self.show_my_list()
            elif active_page == 'history':
                self.show_history()
            return False

        GLib.idle_add(restore_page)


    @staticmethod
    def lastfm_status_text(credentials):
        if credentials['username']:
            return tr(f"Conectado como {credentials['username']}")
        if credentials['pending_token']:
            return tr('Autorize no navegador e conclua a conexão.')
        return tr('Conta não conectada')

    def save_lastfm_settings(self):
        api_key = self.lastfm_api_key_entry.get_text().strip()
        api_secret = self.lastfm_api_secret_entry.get_text().strip()
        old = settings.lastfm_credentials()
        changed = api_key != old['api_key'] or api_secret != old['api_secret']
        settings.set_lastfm_credentials(
            api_key, api_secret,
            session_key='' if changed else None,
            username='' if changed else None,
            pending_token='' if changed else None,
            enabled=self.lastfm_enabled_switch.get_active(),
        )

    def lastfm_enabled_changed(self, switch, *_args):
        try:
            self.save_lastfm_settings()
        except OSError as error:
            self.show_notice(tr(f'Não foi possível salvar a configuração do Last.fm: {error}'))

    def start_lastfm_authorization(self, *_args):
        api_key = self.lastfm_api_key_entry.get_text().strip()
        api_secret = self.lastfm_api_secret_entry.get_text().strip()
        if not api_key or not api_secret:
            self.lastfm_status.set_text(tr('Informe a chave e o segredo da API.'))
            return
        try:
            self.save_lastfm_settings()
        except OSError as error:
            self.lastfm_status.set_text(tr(f'Falha ao salvar: {error}'))
            return
        self.lastfm_connect_button.set_sensitive(False)
        self.lastfm_status.set_text(tr('Solicitando autorização…'))

        def worker():
            try:
                token = lastfm.request_token(api_key, api_secret)
                GLib.idle_add(self.open_lastfm_authorization, api_key, token)
            except Exception as error:
                GLib.idle_add(self.lastfm_authorization_failed, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def open_lastfm_authorization(self, api_key, token):
        try:
            settings.set_lastfm_credentials(
                api_key, self.lastfm_api_secret_entry.get_text().strip(), pending_token=token,
            )
            webbrowser.open(lastfm.authorization_url(api_key, token))
            self.lastfm_status.set_text(tr('Autorize Anime Nyaa no navegador e clique em “Concluir conexão”.'))
            self.lastfm_finish_button.set_visible(True)
        except Exception as error:
            self.lastfm_status.set_text(tr(f'Não foi possível abrir a autorização: {error}'))
        self.lastfm_connect_button.set_sensitive(True)
        return False

    def lastfm_authorization_failed(self, message):
        self.lastfm_status.set_text(message)
        self.lastfm_connect_button.set_sensitive(True)
        return False

    def finish_lastfm_authorization(self, *_args):
        credentials = settings.lastfm_credentials()
        if not credentials['pending_token']:
            self.lastfm_status.set_text(tr('Clique em “Autorizar” e aprove o acesso no navegador primeiro.'))
            return
        self.lastfm_finish_button.set_sensitive(False)
        self.lastfm_status.set_text(tr('Concluindo conexão…'))

        def worker():
            try:
                session_key, username = lastfm.create_session(
                    credentials['api_key'], credentials['api_secret'], credentials['pending_token'],
                )
                settings.set_lastfm_credentials(
                    credentials['api_key'], credentials['api_secret'], session_key=session_key,
                    username=username, pending_token='',
                )
                GLib.idle_add(self.lastfm_connection_succeeded, username)
            except Exception as error:
                GLib.idle_add(self.lastfm_authorization_failed, str(error))
                GLib.idle_add(self.lastfm_finish_button.set_sensitive, True)

        threading.Thread(target=worker, daemon=True).start()

    def lastfm_connection_succeeded(self, username):
        self.lastfm_status.set_text(tr(f'Conectado como {username}'))
        self.lastfm_finish_button.set_visible(False)
        self.lastfm_finish_button.set_sensitive(True)
        return False

    def choose_temporary_directory(self, parent, row):
        chooser = Gtk.FileChooserNative.new(
            tr('Escolher pasta para vídeos temporários'), parent,
            Gtk.FileChooserAction.SELECT_FOLDER, tr('Selecionar'), tr('Cancelar'),
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
                    threading.Thread(target=settings.cleanup_temporary_directory, daemon=True).start()
                except OSError as error:
                    self.show_notice(tr(f'Não foi possível salvar a pasta: {error}'))
        chooser.destroy()
        self.folder_chooser = None

    def reset_temporary_directory(self, row):
        try:
            settings.set_temporary_directory(None)
            row.set_subtitle(str(settings.temporary_directory()))
            threading.Thread(target=settings.cleanup_temporary_directory, daemon=True).start()
        except OSError as error:
            self.show_notice(tr(f'Não foi possível restaurar /tmp: {error}'))

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
    app = AnimeApp(smoke='--smoke-test' in argv)
    status = app.run([argv[0]])
    if app.smoke_error:
        print(f'Bundled GTK icon smoke test failed: {app.smoke_error}', file=sys.stderr)
        return 1
    return status
