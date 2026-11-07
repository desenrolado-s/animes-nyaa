"""Small HTML client for the public Nyaa search page."""
from html.parser import HTMLParser
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class _SearchParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.row = {'title': '', 'magnet': '', 'seeders': '', 'leechers': '', 'downloads': '', 'size': '', 'date': ''}
            self.cell = None
        elif self.row is not None and tag == 'td':
            self.cell = len(self.row.get('_cells', []))
            self.row.setdefault('_cells', []).append('')
        elif self.row is not None and tag == 'a':
            href = attrs.get('href', '')
            if href.startswith('magnet:'):
                self.row['magnet'] = href
            elif self.cell == 1 and href.startswith('/view/'):
                self.anchor = 'title'

    def handle_data(self, data):
        if self.row is None:
            return
        data = data.strip()
        if not data:
            return
        if self.anchor == 'title':
            self.row['title'] += data
        elif self.cell is not None:
            cells = self.row['_cells']
            cells[self.cell] += (' ' if cells[self.cell] else '') + data

    def handle_endtag(self, tag):
        if tag == 'a':
            self.anchor = None
        elif tag == 'tr' and self.row is not None:
            cells = self.row.pop('_cells', [])
            # Nyaa columns: category, name, links, size, date, seeders, leechers, completed.
            for key, index in [('size', 3), ('date', 4), ('seeders', 5), ('leechers', 6), ('downloads', 7)]:
                if index < len(cells):
                    self.row[key] = cells[index]
            if self.row['title'] and self.row['magnet']:
                self.rows.append(self.row)
            self.row = self.cell = None


def search(query, category='1_0', limit=50):
    query = query.strip()
    if not query:
        return []
    url = 'https://nyaa.si/?' + urlencode({'f': '0', 'c': category, 'q': query, 's': 'seeders', 'o': 'desc'})
    request = Request(url, headers={'User-Agent': 'AnimeNyaa/1.0 (desktop app)'})
    with urlopen(request, timeout=20) as response:
        content = response.read(3_000_000).decode('utf-8', errors='replace')
    parser = _SearchParser()
    parser.feed(content)
    return parser.rows[:limit]


TRUSTED_GROUPS = ('erai-raws', 'feibanyama')


def is_trusted_group(title):
    """Check if the release title belongs to a trusted release group."""
    if not title:
        return False
    title_lower = title.lower()
    return any(group in title_lower for group in TRUSTED_GROUPS)


def sort_releases_by_trusted(rows):
    """Sort releases keeping trusted groups at the top, preserving seeders/original order."""
    def _rank(item):
        title = item.get('title', '')
        return (0 if is_trusted_group(title) else 1)

    return sorted(rows, key=_rank)


def is_batch_title(title):
    return bool(re.search(
        r'\b(batch|complete|season|collection|series\s+pack)\b|(?<!\d)\d{1,3}\s*[-~–]\s*\d{1,3}(?!\d)|\b\d{1,3}\s+episodes\b',
        title, re.IGNORECASE,
    ))


def season_number_from_title(title):
    """Return an explicit season number from a catalogue title, if present."""
    match = re.search(r'\bseason[ ._-]*0*(\d{1,2})\b', title, re.IGNORECASE)
    if not match:
        match = re.search(r'(?:^|\s)S0*(\d{1,2})(?=$|\s)', title, re.IGNORECASE)
    return int(match.group(1)) if match else None


def strip_season_from_title(title):
    """Remove a trailing season label so it does not become an Nyaa search term."""
    title = re.sub(
        r'\s*(?:[-:–—]\s*)?(?:season[ ._-]*0*\d{1,2}|S0*\d{1,2})\s*$',
        '', title, flags=re.IGNORECASE,
    )
    return title.strip(' :–—-')


def matches_episode(title, number, season=None):
    number = int(number)
    reversed_season_episode = re.search(
        r'\bE(?:P)?0*(\d{1,3})[ ._-]*S0*(\d{1,2})(?!\d)', title, re.IGNORECASE,
    )
    if reversed_season_episode:
        return (int(reversed_season_episode.group(1)) == number and
                (season is None or int(reversed_season_episode.group(2)) == season))
    season_episode = re.search(
        r'\bS0*(\d{1,2})[ ._-]*E(?:P)?[ ._-]*0*(\d{1,3})(?!\d)',
        title, re.IGNORECASE,
    )
    if season_episode:
        return (int(season_episode.group(2)) == number and
                (season is None or int(season_episode.group(1)) == season))
    explicit_episode = re.search(r'\b(?:EP(?:ISODE)?|E)[ ._-]*0?(\d{1,3})(?!\d)', title, re.IGNORECASE)
    if explicit_episode:
        return int(explicit_episode.group(1)) == number
    pattern = rf'(?<!\d)0?{number}(?!\d)'
    return bool(re.search(pattern, title, re.IGNORECASE))
