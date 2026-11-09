"""MyAnimeList account controls and asynchronous progress synchronization."""
import threading
import webbrowser
from urllib.parse import urlparse

from gi.repository import Adw, GLib, Gtk

from ..services import anilist, mal_callback, mal_sync, myanimelist
from ..storage import settings
from .i18n import tr


class MalUI:
    def build_mal_settings(self):
        credentials = settings.mal_credentials()
        group = Adw.PreferencesGroup(
            title='MyAnimeList',
            description=tr('Acompanhe apenas os animes que você escolher.'))
        self.mal_client_entry = Gtk.Entry(text=credentials['client_id'], hexpand=True)
        row = Adw.ActionRow(title=tr('ID do cliente MyAnimeList'))
        row.add_suffix(self.mal_client_entry)
        group.add(row)
        self.mal_secret_entry = Gtk.PasswordEntry(hexpand=True)
        self.mal_secret_entry.set_text(credentials['client_secret'])
        self.mal_secret_entry.set_show_peek_icon(True)
        row = Adw.ActionRow(title=tr('Segredo do cliente (se houver)'))
        row.add_suffix(self.mal_secret_entry)
        group.add(row)
        self.mal_redirect_entry = Gtk.Entry(text=credentials['redirect_uri'] or 'http://localhost:8765/callback', hexpand=True)
        row = Adw.ActionRow(title=tr('URL de redirecionamento'))
        row.add_suffix(self.mal_redirect_entry)
        group.add(row)
        row = Adw.ActionRow(title=tr('Aplicativo MyAnimeList'),
                            subtitle=tr('Crie um cliente de API e use a mesma URL de redirecionamento.'))
        row.add_suffix(Gtk.LinkButton(uri='https://myanimelist.net/apiconfig', label=tr('Criar cliente')))
        group.add(row)
        row = Adw.ActionRow(title=tr('Conectar conta'))
        self.mal_status = Gtk.Label(label=self.mal_status_text(), xalign=1, wrap=True)
        self.mal_status.set_max_width_chars(28)
        row.add_suffix(self.mal_status)
        self.mal_auth_button = Gtk.Button(label=tr('Autorizar'))
        self.mal_auth_button.connect('clicked', self.start_mal_authorization)
        row.add_suffix(self.mal_auth_button)
        disconnect = Gtk.Button(label=tr('Desconectar'))
        disconnect.connect('clicked', self.disconnect_mal)
        row.add_suffix(disconnect)
        group.add(row)
        row = Adw.ActionRow(title=tr('URL após autorização'),
                            subtitle=tr('Se a conexão automática falhar, cole a URL completa de retorno.'))
        self.mal_callback_entry = Gtk.Entry(hexpand=True)
        row.add_suffix(self.mal_callback_entry)
        finish = Gtk.Button(label=tr('Concluir conexão'))
        finish.connect('clicked', self.finish_mal_authorization)
        row.add_suffix(finish)
        group.add(row)
        return group

    @staticmethod
    def mal_status_text():
        credentials = settings.mal_credentials()
        if credentials['refresh_token']:
            return tr('Conectado ao MyAnimeList')
        return tr('Conta não conectada')

    def start_mal_authorization(self, *_args):
        client_id = self.mal_client_entry.get_text().strip()
        client_secret = self.mal_secret_entry.get_text().strip()
        redirect_uri = self.mal_redirect_entry.get_text().strip()
        parsed = urlparse(redirect_uri)
        if not client_id or parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment:
            self.mal_status.set_text(tr('Informe o ID do cliente e uma URL de redirecionamento válida.'))
            return
        url, verifier, state = myanimelist.new_authorization(client_id, redirect_uri)
        self._stop_mal_listener()
        self._mal_authorization = (client_id, redirect_uri, verifier, state, client_secret)
        pending = self._mal_authorization
        self.mal_callback_entry.set_text('')
        try:
            self._mal_listener = mal_callback.CallbackListener(
                redirect_uri, state,
                lambda code: GLib.idle_add(self._mal_received_code, pending, code),
                tr('Autorização recebida. Volte ao aplicativo para concluir a conexão.'),
                tr('Retorno inválido. Volte ao aplicativo e tente novamente.'))
        except OSError:
            self._mal_authorization = None
            self._mal_listener = None
            self.mal_status.set_text(tr('A porta de retorno está em uso. Feche o outro aplicativo ou escolha outra porta cadastrada no MyAnimeList.'))
            return
        except ValueError:
            self._mal_listener = None
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            self._stop_mal_listener()
            self.mal_status.set_text(tr('Não foi possível abrir o navegador.'))
            return
        self.mal_status.set_text(tr('Autorize no navegador; a conexão será concluída automaticamente.')
                                 if self._mal_listener else
                                 tr('Autorize no navegador e cole a URL de retorno.'))

    def finish_mal_authorization(self, *_args):
        pending = getattr(self, '_mal_authorization', None)
        if not pending:
            self.mal_status.set_text(tr('Inicie a autorização primeiro.'))
            return
        client_id, redirect_uri, verifier, state, client_secret = pending
        try:
            code = myanimelist.callback_code(self.mal_callback_entry.get_text(), redirect_uri, state)
        except ValueError as error:
            self.mal_status.set_text(tr(str(error)))
            return
        self._mal_received_code(pending, code)

    def _stop_mal_listener(self):
        listener = getattr(self, '_mal_listener', None)
        self._mal_listener = None
        if listener:
            listener.close()

    def cancel_mal_authorization(self, *_args):
        self._mal_authorization = None
        self._mal_exchange_pending = False
        self._stop_mal_listener()
        return False

    def _mal_received_code(self, pending, code):
        if pending != getattr(self, '_mal_authorization', None) or getattr(self, '_mal_exchange_pending', False):
            return False
        self._mal_exchange_pending = True
        self._stop_mal_listener()
        client_id, redirect_uri, verifier, state, client_secret = pending
        self.mal_auth_button.set_sensitive(False)
        self.mal_status.set_text(tr('Concluindo conexão…'))

        def worker():
            try:
                tokens = myanimelist.exchange_code(client_id, redirect_uri, verifier, code, client_secret)
                username = myanimelist.user_name(tokens.get('access_token', ''))
                if not username:
                    raise RuntimeError('MyAnimeList did not return a username')
                GLib.idle_add(self._finish_mal_connection, pending, tokens, username, None)
            except Exception as error:
                GLib.idle_add(self._finish_mal_connection, pending, None, '', str(error))
        threading.Thread(target=worker, daemon=True).start()
        return False

    def _finish_mal_connection(self, pending, tokens, username, error):
        if pending != getattr(self, '_mal_authorization', None):
            return False
        self._mal_exchange_pending = False
        self.mal_auth_button.set_sensitive(True)
        if error:
            self.mal_status.set_text(tr('Falha ao conectar ao MyAnimeList.'))
            return False
        try:
            myanimelist.save_tokens(pending[0], pending[1], tokens, username=username, client_secret=pending[4])
        except (OSError, ValueError, RuntimeError):
            self.mal_status.set_text(tr('Falha ao conectar ao MyAnimeList.'))
            return False
        self._mal_authorization = None
        self.mal_callback_entry.set_text('')
        self.mal_status.set_text(self.mal_status_text())
        if self.current_anime:
            self.queue_mal_sync(self.current_anime)
        return False

    def disconnect_mal(self, *_args):
        self.cancel_mal_authorization()
        myanimelist.disconnect()
        self.mal_callback_entry.set_text('')
        self.mal_status.set_text(self.mal_status_text())
        self._mal_status_generation = getattr(self, '_mal_status_generation', 0) + 1
        if self.current_anime:
            self.queue_mal_sync(self.current_anime)

    def queue_mal_sync(self, media, push_through=None):
        if not media:
            return
        media = dict(media)
        credentials = settings.mal_credentials()
        current = (self.current_anime or {}).get('id') == media.get('id')
        tracked = bool(credentials['refresh_token'] and mal_sync.is_tracked(media.get('id')))
        generation = getattr(self, '_mal_status_generation', 0)
        if current:
            generation += 1
            self._mal_status_generation = generation
            self.mal_track_button.set_label(tr('Parar de acompanhar') if tracked else tr('Acompanhar no MyAnimeList'))
            self.mal_track_button.set_sensitive(bool(credentials['refresh_token']))
            self.mal_edit_button.set_sensitive(tracked)
            self.anime_mal_status.set_text(
                tr('Consultando MyAnimeList…') if tracked else
                tr('Este anime não está vinculado.') if credentials['refresh_token'] else
                tr('Conecte sua conta nas configurações.'))
        if not tracked:
            return
        revision = mal_sync.revision(media.get('id'), credentials['username'])
        def worker():
            try:
                if mal_sync.sync(media, push_through=push_through, expected_revision=revision):
                    mal_id = media.get('idMal') or anilist.mal_id(media['id'])
                    status = myanimelist.get_list_status(mal_id)
                    GLib.idle_add(self._mal_sync_finished, media.get('id'), generation,
                                  credentials['username'], status, None)
            except Exception:
                GLib.idle_add(self._mal_sync_finished, media.get('id'), generation,
                              credentials['username'], None, True)
        threading.Thread(target=worker, daemon=True).start()

    def toggle_mal_tracking(self, *_args):
        media = self.current_anime or {}
        anime_id = media.get('id')
        try:
            if mal_sync.set_tracked(anime_id, not mal_sync.is_tracked(anime_id)):
                self.queue_mal_sync(media)
        except OSError:
            self.show_notice(tr('Não foi possível salvar o acompanhamento do MyAnimeList.'))

    def open_mal_editor(self, *_args):
        media = dict(self.current_anime or {})
        if not mal_sync.is_tracked(media.get('id')):
            return
        self.mal_edit_button.set_sensitive(False)
        self.anime_mal_status.set_text(tr('Consultando MyAnimeList…'))

        def worker():
            try:
                mal_id = media.get('idMal') or anilist.mal_id(media['id'])
                if not mal_id:
                    raise ValueError('Missing MAL ID')
                status = myanimelist.get_list_status(mal_id)
                GLib.idle_add(self._show_mal_editor, media, mal_id, status, False)
            except Exception:
                GLib.idle_add(self._show_mal_editor, media, None, None, True)
        threading.Thread(target=worker, daemon=True).start()

    def _show_mal_editor(self, media, mal_id, status, error):
        if (self.current_anime or {}).get('id') != media.get('id') or not mal_sync.is_tracked(media.get('id')):
            return False
        self.mal_edit_button.set_sensitive(True)
        if error:
            self.anime_mal_status.set_text(tr('Não foi possível consultar o MyAnimeList.'))
            return False
        new_entry = not status
        status = status or {}
        username = settings.mal_credentials()['username']
        window = Gtk.Window(title=tr('Editar MyAnimeList'), transient_for=self.window, modal=True)
        window.set_default_size(420, 400)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        window.set_child(box)
        states = ['watching', 'completed', 'on_hold', 'dropped', 'plan_to_watch']
        names = [tr('Assistindo'), tr('Concluído'), tr('Em espera'), tr('Abandonado'), tr('Planejo assistir')]
        box.append(Gtk.Label(label=tr('Situação'), xalign=0))
        state = Gtk.DropDown(model=Gtk.StringList.new(names))
        state.set_selected(states.index(status['status']) if status.get('status') in states else 4)
        box.append(state)
        box.append(Gtk.Label(label=tr('Episódios assistidos'), xalign=0))
        count = Gtk.SpinButton.new_with_range(0, 999999, 1)
        count.set_value(int(status.get('num_episodes_watched') or 0))
        box.append(count)
        box.append(Gtk.Label(label=tr('Nota (0 para não avaliado)'), xalign=0))
        score = Gtk.SpinButton.new_with_range(0, 10, 1)
        score.set_value(int(status.get('score') or 0))
        box.append(score)
        rewatch_row = Gtk.Box(spacing=8)
        rewatch_label = Gtk.Label(label=tr('Reassistindo'), xalign=0, hexpand=True)
        rewatch_row.append(rewatch_label)
        rewatch = Gtk.Switch(active=bool(status.get('is_rewatching')))
        rewatch_row.append(rewatch)
        box.append(rewatch_row)
        box.append(Gtk.Label(label=tr('Vezes que reassistiu') if 'num_times_rewatched' in status else
                             tr('Vezes que reassistiu (valor não informado pelo MyAnimeList)'), xalign=0, wrap=True))
        rewatch_count = Gtk.SpinButton.new_with_range(0, 9999, 1)
        rewatch_count.set_value(int(status.get('num_times_rewatched') or 0))
        box.append(rewatch_count)
        rewatch_count_changed = [False]
        rewatch_count.connect('value-changed', lambda *_: rewatch_count_changed.__setitem__(0, True))
        initial = (state.get_selected(), count.get_value_as_int(), score.get_value_as_int(),
                   rewatch.get_active(), rewatch_count.get_value_as_int())
        feedback = Gtk.Label(label='', wrap=True, xalign=0)
        box.append(feedback)
        save = Gtk.Button(label=tr('Salvar no MyAnimeList'))
        save.add_css_class('suggested-action')
        box.append(save)

        def save_clicked(_button):
            if not mal_sync.is_tracked(media['id']):
                feedback.set_text(tr('Este anime não está vinculado.'))
                return
            current = (state.get_selected(), count.get_value_as_int(), score.get_value_as_int(),
                       rewatch.get_active(), rewatch_count.get_value_as_int())
            changes = {}
            if new_entry or current[0] != initial[0]:
                changes['status'] = states[current[0]]
            if current[1] != initial[1]:
                changes['num_watched_episodes'] = current[1]
            if current[2] != initial[2]:
                changes['score'] = current[2]
            if current[3] != initial[3]:
                changes['is_rewatching'] = 'true' if current[3] else 'false'
            if rewatch_count_changed[0]:
                changes['num_times_rewatched'] = current[4]
            if not changes:
                window.close()
                return
            save.set_sensitive(False)
            feedback.set_text(tr('Salvando…'))
            mal_sync.reserve_manual_edit(media['id'], username)
            def worker():
                try:
                    mal_sync.save_manual(media['id'], mal_id, username, changes)
                    GLib.idle_add(done, None)
                except Exception:
                    GLib.idle_add(done, True)
            threading.Thread(target=worker, daemon=True).start()

        def done(error):
            if error:
                save.set_sensitive(True)
                feedback.set_text(tr('Não foi possível salvar no MyAnimeList.'))
            else:
                window.close()
                if (self.current_anime or {}).get('id') == media['id']:
                    self.queue_mal_sync(media)
            return False

        save.connect('clicked', save_clicked)
        window.present()
        return False

    def _mal_sync_finished(self, anime_id, generation, username, status, error):
        credentials = settings.mal_credentials()
        if ((self.current_anime or {}).get('id') != anime_id or
                generation != getattr(self, '_mal_status_generation', 0) or
                not credentials['refresh_token'] or credentials['username'] != username):
            return False
        self.refresh_watched_episodes()
        if error:
            self.anime_mal_status.set_text(tr('Não foi possível consultar o MyAnimeList.'))
            self.show_notice(tr('Falha ao sincronizar com MyAnimeList. Tente novamente ao abrir o anime.'))
        else:
            self.anime_mal_status.set_text(self.format_mal_anime_status(status))
        return False

    @staticmethod
    def format_mal_anime_status(status):
        if not status:
            return tr('Este anime ainda não está na sua lista do MyAnimeList.')
        labels = {'watching': 'Assistindo', 'completed': 'Concluído', 'on_hold': 'Em espera',
                  'dropped': 'Abandonado', 'plan_to_watch': 'Planejo assistir'}
        state = tr(labels.get(status.get('status'), 'Status desconhecido'))
        episodes = int(status.get('num_episodes_watched') or 0)
        score = int(status.get('score') or 0)
        result = tr('{status} · {count} episódio(s) assistido(s)').format(status=state, count=episodes)
        if score:
            result += ' · ' + tr('Nota: {score}/10').format(score=score)
        return result
