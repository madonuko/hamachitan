import html
import re
from datetime import datetime
import dateparser
import json
from prompt_toolkit import prompt
import asyncio
import aiohttp

from bs4 import BeautifulSoup

import mwparserfromhell as mw
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import ExistingPageBot
from link_detector import LinkDetectorBot

RE_WEBARCHIVE = re.compile(r'^https://web\.archive\.org/web/(\d{4})(\d{2})(\d{2})')

REQ_HEADERS = {'User-Agent': 'atl.wiki/User:Hamachitan', 'From': 'mado@fyralabs.com'}
DEAD_LINK_TEMPLATE = 'Dead Link'


class TidyRefsBot(ExistingPageBot):
    update_options = {
        'summary': '/* References */ 🍣 Fix [[ATL:Guidelines#Citations|citations]]'
    }
    session: aiohttp.ClientSession

    def treat_page(self):
        page = self.current_page
        if not page.exists():
            print(f'[[{page.title()}]] does not exist')
            return
        if not page.has_permission():
            print(f'[[{page.title()}]] no perms')
            return
        wikicode = asyncio.run(self.process_wikicode(mw.parse(page.text)))
        self.put_current(str(wikicode), summary=self.opt.summary)

    async def process_wikicode(
        self, wikicode: mw.wikicode.Wikicode
    ) -> mw.wikicode.Wikicode:
        self.session = aiohttp.ClientSession(headers=REQ_HEADERS)
        tasks = []
        tags = []
        for tag in wikicode.ifilter_tags(matches=lambda tag: tag.tag == 'ref'):
            tag.contents = mw.parse(tag.contents.strip())
            if (
                len(tag.contents.nodes) == 1
                and isinstance(tag.contents.nodes[0], mw.nodes.ExternalLink)
                and not tag.contents.nodes[0].url.endswith('}}')
                and not LinkDetectorBot.find_template(wikicode, tag)
            ):
                tasks.append(
                    asyncio.create_task(self.process_url(tag.contents.nodes[0]))
                )
                tags.append(tag)
        results = await asyncio.gather(*tasks)
        for tag, result in zip(tags, results):
            tag.contents = result
        await self.session.close()
        return wikicode

    @staticmethod
    def format_date(date: str) -> str:
        if date := dateparser.parse(date):
            return date.strftime('%Y-%m-%d')
        return ''

    async def get_publish_date(self, resp, soup: BeautifulSoup) -> str:
        return (
            await self._extract_full_date(resp, soup)
            or await self._extract_year(soup)
            or ''
        )

    async def _extract_full_date(self, resp, soup: BeautifulSoup) -> str:
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
        for time_tag in soup.find_all('time', datetime=True):
            if date := self.format_date(time_tag.get('datetime', '')):
                return date
        if last_modified := resp.headers.get('Last-Modified'):
            if date := self.format_date(last_modified):
                return date
        return ''

    async def _extract_year(self, soup: BeautifulSoup) -> str:
        current_year = datetime.now().year
        year_patterns = [
            {'attr': 'name', 'val': 'dc.date.issued'},
            {'attr': 'name', 'val': 'citation_publication_date'},
            {'attr': 'name', 'val': 'citation_date'},
            {'attr': 'name', 'val': 'parsely-pub-date'},
            {'attr': 'name', 'val': 'publish-date'},
            {'attr': 'name', 'val': 'copyright'},
            {'attr': 'name', 'val': 'creationdate'},
            {'attr': 'name', 'val': 'dc.creator'},
            {'attr': 'name', 'val': 'dc.date.created'},
            {'attr': 'name', 'val': 'article:published'},
            {'attr': 'name', 'val': 'originalpublicationdate'},
            {'attr': 'name', 'val': 'shareaholic:article_published_time'},
            {'attr': 'name', 'val': 'timestamp'},
        ]
        for pattern in year_patterns:
            if tag := soup.find('meta', {pattern['attr']: pattern['val']}):
                if year_match := re.search(
                    r'\b(19\d{2}|20[0-2]\d)\b', tag.get('content', '')
                ):
                    year = int(year_match.group())
                    if 1990 <= year <= current_year:
                        return str(year)
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

    async def process_url(self, node: mw.nodes.ExternalLink) -> mw.wikicode.Wikicode:
        url = node.url
        print(flush=True, end=f'GET {url} ')
        today = datetime.today().strftime('%Y-%m-%d')
        try:
            async with self.session.get(url, allow_redirects=True) as resp:
                text = await resp.text()
                soup = BeautifulSoup(text, 'html.parser')
                title = ''
                if soup.title:
                    title = soup.title.string
                print(f'-> {title}')
        except Exception as e:
            print(f'FAIL: {e}')
            return mw.parse(f'{node}{{{{{DEAD_LINK_TEMPLATE}|{today}|{e}}}}}')
        if not resp.ok:
            print(f'-> {resp.status}')
            return mw.parse(f'{node}{{{{{DEAD_LINK_TEMPLATE}|{today}|{resp.status}}}}}')
        if not all(ch not in title for ch in '[]{}<>'):
            title = f'<nowiki>{html.escape(title)}</nowiki>'
        title = await asyncio.to_thread(prompt, ' ■ Title  : ', default=title)
        title = title.strip()
        if title.startswith('err '):
            title = title.removeprefix('err ')
            return mw.parse(f'{node}{{{{{DEAD_LINK_TEMPLATE}|{today}|{title}}}}}')
        if match := RE_WEBARCHIVE.match(url):
            today = f'{match.group(1)}-{match.group(2)}-{match.group(3)}'
        today = await asyncio.to_thread(prompt, ' ■ Access : ', default=today)
        today = today.strip()
        author = await asyncio.to_thread(prompt, ' ■ Author : ')
        author = author.strip()
        if author:
            author = ', ' + author
        create_date = await asyncio.to_thread(
            prompt, ' ■ Create : ', default=await self.get_publish_date(resp, soup)
        )
        if create_date := self.format_date(create_date):
            date_part = f', {create_date}'
        else:
            date_part = ''
        return mw.parse(f'[{url} {title}]{author}{date_part} (Accessed: {today})')


def main(*args: str) -> None:
    options = {}
    gen_factory = pagegenerators.GeneratorFactory()
    local_args = pywikibot.handle_args(args)
    local_args = gen_factory.handle_args(local_args)
    for arg in local_args:
        opt, sep, value = arg.partition(':')
        if opt in ('-summary'):
            options[opt[1:]] = value
    TidyRefsBot(generator=gen_factory.getCombinedGenerator(), **options).run()


if __name__ == '__main__':
    main()
