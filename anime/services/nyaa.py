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


def is_batch_title(title):
    return bool(re.search(
        r'\b(batch|complete|season|collection|series\s+pack)\b|(?<!\d)\d{1,3}\s*[-~–]\s*\d{1,3}(?!\d)|\b\d{1,3}\s+episodes\b',
        title, re.IGNORECASE,
    ))


def matches_episode(title, number):
    number = int(number)
    season_episode = re.search(r'\bS\d{1,2}[ ._-]*E(?:P)?[ ._-]*0?(\d{1,3})(?!\d)', title, re.IGNORECASE)
    if season_episode:
        return int(season_episode.group(1)) == number
    explicit_episode = re.search(r'\b(?:EP(?:ISODE)?|E)[ ._-]*0?(\d{1,3})(?!\d)', title, re.IGNORECASE)
    if explicit_episode:
        return int(explicit_episode.group(1)) == number
    pattern = rf'(?<!\d)0?{number}(?!\d)'
    return bool(re.search(pattern, title, re.IGNORECASE))
