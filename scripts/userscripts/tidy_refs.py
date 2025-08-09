import html
import re
from datetime import datetime
import dateparser
import json
import readline
from prompt_toolkit import prompt

import requests
from bs4 import BeautifulSoup

import mwparserfromhell as mw
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import ExistingPageBot

# RE_DOMAIN = re.compile(r'^.+?://([^/]+)/?')
RE_WEBARCHIVE = re.compile(r'^https://web\.archive\.org/web/(\d{4})(\d{2})(\d{2})')

REQ_HEADERS = {'User-Agent': 'atl.wiki/User:Hamachitan', 'From': 'mado@fyralabs.com'}


class TidyRefsBot(ExistingPageBot):
    update_options = {
        # 'text': 'text to update',
        'summary': '/* References */ 🍣 Tidy up format, see [[ATL:Guidelines#Citations]]'
    }

    def treat_page(self):
        page = self.current_page
        if not page.exists():
            print(f'[[{page.title()}]] does not exist')
            return
        if not page.has_permission():
            print(f'[[{page.title()}]] no perms')
            return
        wikicode = self.process_wikicode(mw.parse(page.text))

        self.put_current(str(wikicode), summary=self.opt.summary)

    def process_wikicode(self, wikicode: mw.wikicode.Wikicode) -> mw.wikicode.Wikicode:
        for tag in wikicode.ifilter_tags(matches='ref'):
            tag.contents = mw.parse(tag.contents.strip())
            if len(tag.contents.nodes) == 1 and isinstance(
                tag.contents.nodes[0], mw.nodes.ExternalLink
            ):
                tag.contents = self.process_url(str(tag.contents.nodes[0].url))
        return wikicode

    @staticmethod
    def format_date(date: str) -> str:
        if date := dateparser.parse(date):
            return date.strftime('%Y-%m-%d')
        return ''

    def get_publish_date(self, req: requests.Request, soup: BeautifulSoup) -> str:
        """Extract publication date with fallback to year-only."""
        return self._extract_full_date(req, soup) or self._extract_year(soup) or ''

    def _extract_full_date(self, req: requests.Request, soup: BeautifulSoup) -> str:
        """Extract YYYY-MM-DD formatted date using common patterns."""
        # Priority 1: Standard meta tags
        meta_patterns = [
            {'attr': 'name', 'val': 'lastmod'},
            {'attr': 'property', 'val': 'article:published_time'},
            {'attr': 'property', 'val': 'og:published_time'},
            {'attr': 'itemprop', 'val': 'datePublished'},
            {'attr': 'name', 'val': 'article.published'},
            {'attr': 'name', 'val': 'bt:pubDate'},
            {'attr': 'name', 'val': 'publish_date'},
            {'attr': 'pubdate', 'val': 'pubdate'},
            {'attr': 'name', 'val': 'sailthru.date'},
            {'attr': 'name', 'val': 'pagerender'},
            {'attr': 'name', 'val': 'dc.date'},
            {'attr': 'name', 'val': 'date'},
        ]

        for pattern in meta_patterns:
            if tag := soup.find('meta', {pattern['attr']: pattern['val']}):
                if date := self.format_date(tag.get('content', '')):
                    return date

        # Priority 2: JSON-LD structured data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                for item in data if isinstance(data, list) else [data]:
                    for key in [
                        'datePublished',
                        'dateCreated',
                        'uploadDate',
                        'pubDate',
                    ]:
                        if value := item.get(key):
                            if date := self.format_date(value):
                                return date
            except (json.JSONDecodeError, TypeError):
                continue

        # Priority 3: Time elements
        for time_tag in soup.find_all('time', datetime=True):
            if date := self.format_date(time_tag.get('datetime', '')):
                return date

        # Priority 4: HTTP headers (Last-Modified as fallback)
        if last_modified := req.headers.get('Last-Modified'):
            if date := self.format_date(last_modified):
                return date

        return ''

    def _extract_year(self, soup: BeautifulSoup) -> str:
        """Extract publication year using extended patterns."""
        current_year = datetime.now().year
        year_patterns = [
            # Standard date patterns that might contain only year
            {'attr': 'name', 'val': 'dc.date.issued'},
            {'attr': 'name', 'val': 'citation_publication_date'},
            {'attr': 'name', 'val': 'citation_date'},
            {'attr': 'name', 'val': 'parsely-pub-date'},
            {'attr': 'name', 'val': 'publish-date'},
            # Copyright and creation patterns
            {'attr': 'name', 'val': 'copyright'},
            {'attr': 'name', 'val': 'creationdate'},
            {'attr': 'name', 'val': 'dc.creator'},
            {'attr': 'name', 'val': 'dc.date.created'},
            # SEO and CMS specific
            {'attr': 'name', 'val': 'article:published'},
            {'attr': 'name', 'val': 'originalpublicationdate'},
            {'attr': 'name', 'val': 'shareaholic:article_published_time'},
            {'attr': 'name', 'val': 'timestamp'},
        ]

        # 1. Check meta tags specifically for years
        for pattern in year_patterns:
            if tag := soup.find('meta', {pattern['attr']: pattern['val']}):
                if year_match := re.search(
                    r'\b(19\d{2}|20[0-2]\d)\b', tag.get('content', '')
                ):
                    year = int(year_match.group())
                    if 1990 <= year <= current_year:
                        return str(year)

        # 2. Check visible elements with year-like patterns
        year_indicators = [
            'copyright',
            '©',
            'published',
            'posted',
            'created',
            'last updated',
            'date',
            'year',
        ]
        for indicator in year_indicators:
            for element in soup.find_all(string=re.compile(indicator, re.I)):
                if year_match := re.search(r'\b(19\d{2}|20[0-2]\d)\b', element):
                    year = int(year_match.group())
                    if 1990 <= year <= current_year:
                        return str(year)

        # 3. Check JSON-LD for year-only values
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                for item in data if isinstance(data, list) else [data]:
                    for key in ['copyrightYear', 'datePublished', 'year']:
                        if value := item.get(key):
                            if year_match := re.search(
                                r'\b(19\d{2}|20[0-2]\d)\b', str(value)
                            ):
                                year = int(year_match.group())
                                if 1990 <= year <= current_year:
                                    return str(year)
            except (json.JSONDecodeError, TypeError):
                continue

        return ''

    def process_url(self, url: str) -> mw.wikicode.Wikicode:
        print(flush=True, end=f'GET {url} ')
        try:
            req = requests.get(url, allow_redirects=True, headers=REQ_HEADERS)
            soup = BeautifulSoup(req.text, 'html.parser')
            title = ''
            if soup.title:
                title = soup.title.string
            print(f'-> {title}')
        except Exception as e:
            print(f'FAIL: {e}')
            return mw.parse(f'[{url} <span style="color:#fc493b">{url} <sup>🍣DEAD?]')
        if not req.ok:
            print(f'-> {req.status_code}')
            return mw.parse(
                f'[{url} <span style="color:#fc493b">{url} <sup>🍣{req.status_code}]'
            )
        if not all(ch not in title for ch in '[]{}<>'):
            title = f'<nowiki>{html.escape(title)}</nowiki>'
        title = prompt(' ■ Title  : ', default=title).strip()
        if match := RE_WEBARCHIVE.match(url):
            today = f'{match.group(1)}-{match.group(2)}-{match.group(3)}'
        else:
            today = datetime.today().strftime('%Y-%m-%d')
        today = prompt(' ■ Access : ', default=today).strip()
        # author = RE_DOMAIN.search(url).group(1)
        if author := prompt(' ■ Author : ').strip():
            author = ', ' + author
        create_date = prompt(' ■ Create : ', default=self.get_publish_date(req, soup))
        if create_date := self.format_date(create_date):
            date_part = f', {create_date}'
        else:
            date_part = ''

        return mw.parse(f'[{url} {title}]{author}{date_part} (Accessed: {today})')


def main(*args: str) -> None:
    """Parse command line arguments and invoke bot."""
    options = {}
    gen_factory = pagegenerators.GeneratorFactory()
    # Option parsing
    local_args = pywikibot.handle_args(args)  # global options
    local_args = gen_factory.handle_args(local_args)  # generators options
    for arg in local_args:
        opt, sep, value = arg.partition(':')
        if opt in ('-summary'):
            options[opt[1:]] = value
    TidyRefsBot(generator=gen_factory.getCombinedGenerator(), **options).run()


if __name__ == '__main__':
    main()
