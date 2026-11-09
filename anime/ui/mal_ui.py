"""MyAnimeList account controls and asynchronous progress synchronization."""
import threading
import webbrowser
from urllib.parse import urlparse

from gi.repository import Adw, GLib, Gtk

from ..services import anilist, mal_sync, myanimelist
from ..storage import settings
from .i18n import tr


class MalUI:
    def build_mal_settings(self):
        credentials = settings.mal_credentials()
        group = Adw.PreferencesGroup(
            title='MyAnimeList',
            description=tr('Sincronize o progresso sequencial ao abrir ou assistir um anime.'))
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
                            subtitle=tr('Copie a URL completa da página aberta após autorizar, mesmo se ela não carregar.'))
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
        self._mal_authorization = (client_id, redirect_uri, verifier, state, client_secret)
        self.mal_callback_entry.set_text('')
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            self.mal_status.set_text(tr('Não foi possível abrir o navegador.'))
            return
        self.mal_status.set_text(tr('Autorize no navegador e cole a URL de retorno.'))

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

    def _finish_mal_connection(self, pending, tokens, username, error):
        self.mal_auth_button.set_sensitive(True)
        if pending != getattr(self, '_mal_authorization', None):
            return False
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
        self._mal_authorization = None
        myanimelist.disconnect()
        self.mal_callback_entry.set_text('')
        self.mal_status.set_text(self.mal_status_text())
        self._mal_status_generation = getattr(self, '_mal_status_generation', 0) + 1
        if self.current_anime:
            self.anime_mal_status.set_text(tr('Conecte sua conta nas configurações.'))

    def queue_mal_sync(self, media):
        if not media:
            return
        media = dict(media)
        credentials = settings.mal_credentials()
        current = (self.current_anime or {}).get('id') == media.get('id')
        generation = getattr(self, '_mal_status_generation', 0)
        if current:
            generation += 1
            self._mal_status_generation = generation
            self.anime_mal_status.set_text(tr('Consultando MyAnimeList…') if credentials['refresh_token']
                                           else tr('Conecte sua conta nas configurações.'))
        if not credentials['refresh_token']:
            return
        def worker():
            try:
                if mal_sync.sync(media):
                    mal_id = media.get('idMal') or anilist.mal_id(media['id'])
                    status = myanimelist.get_list_status(mal_id)
                    GLib.idle_add(self._mal_sync_finished, media.get('id'), generation,
                                  credentials['username'], status, None)
            except Exception:
                GLib.idle_add(self._mal_sync_finished, media.get('id'), generation,
                              credentials['username'], None, True)
        threading.Thread(target=worker, daemon=True).start()

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
