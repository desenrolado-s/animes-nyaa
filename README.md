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

As versões Linux publicadas incluem um pacote executável `.tar.gz`, um arquivo com o código-fonte e `SHA256SUMS.txt`. Extraia o pacote executável e rode `./anime-nyaa`; GTK 4, Libadwaita, mpv, Node.js e WebTorrent CLI precisam estar instalados no sistema. O pacote executável inclui o interpretador Python e os módulos do aplicativo.

Use a barra lateral para navegar pelo catálogo, pela **Minha lista** e pelo **Histórico**, ou para escolher a categoria dos torrents. Na ficha do anime, **Minha lista** salva ou remove o anime da sua lista pessoal. Cada episódio procura no Nyaa tanto pelo número com zero à esquerda (por exemplo, `01`) quanto sem ele (`1`); a consulta usada pode ser conferida e editada nos resultados, com um padrão adicional opcional. Na aba **Batches**, escolha um torrent para carregar os arquivos de vídeo que ele contém; cada episódio pode ser aberto individualmente no mpv. Use a estrela em um batch para mantê-lo no topo dos resultados daquele anime.

Abra **Configurações** no botão de engrenagem para escolher a pasta usada pelo WebTorrent durante a reprodução e configurar a integração com o Last.fm. Para conectar, crie uma chave de API em [last.fm/api/account/create](https://www.last.fm/api/account/create), informe a chave e o segredo nas configurações, clique em **Autorizar** e conclua a conexão depois de aprovar o acesso no navegador. Na primeira reprodução de cada episódio, o app consulta os temas no AnimeThemes e envia a abertura e o encerramento ao Last.fm. Se o envio falhar, uma reprodução posterior tentará novamente; depois que o Last.fm aceitar os temas, o app não os envia de novo. As preferências e credenciais ficam em `~/.local/share/anime-nyaa/settings.json`. Se nenhuma pasta temporária for escolhida, os vídeos ficam em `/tmp`. Os dados de cada sessão são removidos quando o WebTorrent encerra.

O histórico fica em `~/.local/share/anime-nyaa/history.json` e pode ser reproduzido, removido por item ou limpo pela página **Histórico**. Episódios iniciados para reprodução são marcados como assistidos, com o progresso salvo em `~/.local/share/anime-nyaa/watch-progress.json`. A lista pessoal e os batches favoritos ficam em `~/.local/share/anime-nyaa/library.json`.

## Adicionar ao menu de aplicativos

Adicione o diretório do projeto ao `PATH` (por exemplo, criando um link em `~/.local/bin`) e copie `packaging/linux/anime-nyaa.desktop` para `~/.local/share/applications/`.

## Estrutura

- `anime_app.py`: ponto de entrada GTK.
- `anime/application.py`: inicialização da janela e composição dos componentes.
- `anime/ui/`: páginas GTK do catálogo, ficha, resultados, histórico e lista pessoal, além de helpers compartilhados.
- `anime/services/`: integração com AniList e Nyaa, identificação de títulos de episódios e operações de torrent.
- `anime/storage/`: persistência do histórico e da lista pessoal, além das preferências locais.
- `anime/application.py`: inicialização da janela e composição das páginas.
- `anime_app.py`: ponto de entrada GTK.
- `anime-nyaa`: lançador do app.

Capas são baixadas sob demanda e armazenadas em `~/.cache/anime-nyaa/covers/` para reutilização offline.

## Releases

Cada push na branch `main` executa os testes, empacota o aplicativo Linux x86_64 com PyInstaller e publica uma GitHub Release com o pacote executável, o código-fonte e seus checksums SHA-256. A versão é incrementada automaticamente a partir das tags existentes (`v1.0.0` → `v1.0.1`); os pacotes incluem a tag no nome. O bundle usa as bibliotecas GTK e Libadwaita do sistema.
