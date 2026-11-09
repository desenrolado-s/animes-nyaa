"""Torrent metadata helpers used to browse the episodes inside batch releases."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

VIDEO_EXTENSIONS = {
    '.avi', '.m2ts', '.m4v', '.mkv', '.mov', '.mp4', '.mpeg', '.mpg',
    '.ogv', '.ts', '.webm', '.wmv',
}
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def resolve_webtorrent_cli_script(executable=None):
    """Resolve the underlying webtorrent-cli JavaScript entry point when available."""
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        bundled = Path(bundle) / 'webtorrent-cli' / 'node_modules' / 'webtorrent-cli' / 'bin' / 'cmd.js'
        if bundled.is_file():
            return str(bundled)
    if executable:
        try:
            resolved = Path(executable).resolve()
        except OSError:
            resolved = Path(executable)
        if resolved.suffix.lower() in ('.js', '.mjs', '.cjs') and resolved.is_file():
            return str(resolved)
        candidates = (
            resolved.parent.parent / 'webtorrent-cli' / 'bin' / 'cmd.js',
            resolved.parent / 'node_modules' / 'webtorrent-cli' / 'bin' / 'cmd.js',
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def list_video_files(magnet, timeout=120):
    executable = shutil.which('webtorrent')
    script = resolve_webtorrent_cli_script(executable)
    use_node_script = bool(
        script and (
            not executable
            or sys.platform == 'win32'
            or executable.lower().endswith(('.cmd', '.bat', '.ps1'))
        )
    )
    node = shutil.which('node') if use_node_script else None
    if node and script:
        command = [node, script, magnet, '--select', 'list', '--quiet', '--port', '0']
    elif executable:
        command = [executable, magnet, '--select', 'list', '--quiet', '--port', '0']
    else:
        raise RuntimeError('Instale webtorrent-cli para ver os episódios deste batch.')
    run_kwargs = {}
    if sys.platform == 'win32':
        run_kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with tempfile.TemporaryDirectory(prefix='anime-nyaa-list-') as temp_dir:
        try:
            result = subprocess.run(
                command,
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=timeout, check=False, cwd=temp_dir,
                **run_kwargs,
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
