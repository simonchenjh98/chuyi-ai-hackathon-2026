"""Validate public page resources and navigation without a browser."""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parent.parent

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.refs, self.tabs = [], [], []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        for key in ('src', 'href'):
            if attrs.get(key):
                self.refs.append(attrs[key])
        if attrs.get('data-day'):
            self.tabs.append(attrs['data-day'])

for file in ('index.html', 'platform.html'):
    page = Page()
    page.feed((ROOT / file).read_text(encoding='utf-8'))
    assert len(page.ids) == len(set(page.ids)), f'Duplicate IDs in {file}'
    for ref in page.refs:
        url = urlsplit(ref)
        if url.scheme or url.netloc:
            assert url.scheme == 'https', f'Insecure public URL: {ref}'
            continue
        if (file == 'platform.html' and not url.path or url.path == 'platform.html') and url.fragment in {'board','judge','audience','admin','board-roadshow','board-final','judge-roadshow','judge-final'}:
            continue
        if url.path.startswith('api/'):
            continue
        target = ROOT / unquote(url.path) if url.path else ROOT / file
        assert target.is_file(), f'Missing resource: {ref} in {file}'
        if url.fragment:
            destination = page
            if url.path:
                destination = Page()
                destination.feed(target.read_text(encoding='utf-8'))
            assert url.fragment in destination.ids, f'Missing anchor: {ref}'
    for tab in page.tabs:
        assert tab in page.ids, f'Missing schedule panel: {tab}'

teams = json.loads((ROOT / 'event-data' / 'teams.public.json').read_text(encoding='utf-8'))
assert len(teams) == 23 and [team['number'] for team in teams] == list(range(1, 24)), 'Expected public teams 1 through 23'
assert all(set(team) == {'number', 'name', 'project', 'track'} for team in teams), 'Public team data contains unexpected fields'
assert all(team['name'].strip() and team['project'].strip() for team in teams), 'Public team names and projects are required'
assert all(team['track'] in {'现实问题', '帮助学习', '研究探索', '创意小游戏', '待确认'} for team in teams), 'Unexpected public track'
print('Public resources, anchors, schedule panels, team data and HTTPS links: passed')
