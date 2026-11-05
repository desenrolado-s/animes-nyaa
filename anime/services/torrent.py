"""Torrent metadata helpers used to browse the episodes inside batch releases."""
import re
import shutil
import subprocess

VIDEO_EXTENSIONS = {
    '.avi', '.m2ts', '.m4v', '.mkv', '.mov', '.mp4', '.mpeg', '.mpg',
    '.ogv', '.ts', '.webm', '.wmv',
}
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def list_video_files(magnet, timeout=120):
    executable = shutil.which('webtorrent')
    if not executable:
        raise RuntimeError('Instale webtorrent-cli para ver os episódios deste batch.')
    try:
        result = subprocess.run(
            [executable, magnet, '--select', 'list', '--quiet'],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('O Nyaa demorou para entregar os dados do torrent. Tente novamente.') from error
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or 'Não foi possível ler os arquivos do torrent.'
        raise RuntimeError(message[-600:])

    files = []
    for line in result.stdout.splitlines():
        # webtorrent-cli may decorate its index/size with terminal color codes,
        # depending on the version and how it detects the calling terminal.
        line = _ANSI_ESCAPE.sub('', line).strip()
        match = re.match(r'^(\d+)\s+(.+?)\s+\(([^()]*)\)\s*$', line)
        if not match:
            # Keep the filename usable if a future CLI changes only the size
            # decoration while retaining its documented leading file index.
            match = re.match(r'^(\d+)\s+(.+)$', line)
        if not match:
            continue
        index, name, *size = match.groups()
        size = size[0] if size else ''
        name = name.strip()
        if name.lower().endswith(tuple(VIDEO_EXTENSIONS)):
            files.append({'index': int(index), 'name': name, 'size': size})
    if not files:
        raise RuntimeError('Este batch não contém arquivos de vídeo reconhecidos.')
    return files


def episode_number(filename):
    season = re.search(r'\bS\d{1,2}[ ._-]*E(?:P)?0*(\d{1,3})(?!\d)', filename, re.IGNORECASE)
    if season:
        return int(season.group(1))
    explicit = re.search(r'\b(?:EP(?:ISODE)?)[ ._-]*0*(\d{1,3})(?!\d)', filename, re.IGNORECASE)
    if explicit:
        return int(explicit.group(1))
    after_separator = re.search(r'[-~–]\s*0*(\d{1,3})(?=\s|[._\[(]|$)', filename)
    if after_separator:
        return int(after_separator.group(1))
    candidates = re.findall(r'(?<!\d)0*(\d{1,3})(?!\d)', filename)
    return int(candidates[-1]) if candidates else None
