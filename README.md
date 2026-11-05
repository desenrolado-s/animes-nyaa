# Anime Nyaa

App desktop GTK 4 que usa o catálogo público do AniList para descobrir animes, mostrar títulos e capas e buscar releases correspondentes no Nyaa. Os torrents são transmitidos pelo WebTorrent e abertos no mpv. O app também mantém histórico local e permite iniciar novamente um item do histórico.

<img width="1912" height="1027" alt="image" src="https://github.com/user-attachments/assets/2b2a4c60-21a2-45b9-9f4c-c48b2bcd39a2" />


## Requisitos

- Linux com GTK 4, Libadwaita e PyGObject
- Python 3
- mpv
- Node.js/npm e WebTorrent CLI (`npm install --global webtorrent-cli`)

No Debian/Ubuntu, as dependências do sistema podem ser instaladas com:

```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 mpv nodejs npm
npm install --global webtorrent-cli
```

## Executar

```sh
./anime-nyaa
```

Use a barra lateral para navegar pelo catálogo, pela **Minha lista** e pelo **Histórico**, ou para escolher a categoria dos torrents. Na ficha do anime, **Minha lista** salva ou remove o anime da sua lista pessoal. Cada episódio procura no Nyaa tanto pelo número com zero à esquerda (por exemplo, `01`) quanto sem ele (`1`); a consulta usada pode ser conferida e editada nos resultados, com um padrão adicional opcional. Na aba **Batches**, escolha um torrent para carregar os arquivos de vídeo que ele contém; cada episódio pode ser aberto individualmente no mpv. Use a estrela em um batch para mantê-lo no topo dos resultados daquele anime.

Abra **Configurações** no botão de engrenagem para escolher a pasta usada pelo WebTorrent durante a reprodução. Se nenhuma pasta for escolhida, os vídeos temporários são armazenados em `/tmp`.

O histórico fica em `~/.local/share/anime-nyaa/history.json` e pode ser reproduzido, removido por item ou limpo pela página **Histórico**. A lista pessoal e os batches favoritos ficam em `~/.local/share/anime-nyaa/library.json`.

## Adicionar ao menu de aplicativos

Adicione o diretório do projeto ao `PATH` (por exemplo, criando um link em `~/.local/bin`) e copie `packaging/linux/anime-nyaa.desktop` para `~/.local/share/applications/`.

## Estrutura

- `anime_app.py`: ponto de entrada GTK.
- `anime/application.py`: inicialização da janela e composição dos componentes.
- `anime/ui_common.py`: estilos e helpers GTK compartilhados.
- `anime/catalog_ui.py`: catálogo AniList, busca e capas.
- `anime/detail_ui.py`: ficha do anime, episódios e navegação de batches.
- `anime/results_ui.py`: releases Nyaa, arquivos de batch e reprodução no mpv.
- `anime/history_ui.py`: página do histórico.
- `anime/library.py` e `anime/library_ui.py`: persistência e interface da lista pessoal e dos batches favoritos.
- `anime/anilist.py`: busca do catálogo em alta e busca de títulos via AniList GraphQL.
- `anime/nyaa.py`: consulta e leitura dos resultados do Nyaa.
- `anime/torrent.py`: lista os episódios de vídeo dentro de um batch torrent.
- `anime/history.py`: persistência do histórico local.
- `anime/settings.py`: preferências locais, incluindo a pasta dos vídeos temporários.
- `anime-nyaa`: lançador do app.

Capas são baixadas sob demanda e armazenadas em `~/.cache/anime-nyaa/covers/` para reutilização offline.
