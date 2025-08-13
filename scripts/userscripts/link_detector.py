import requests
import mwparserfromhell as mw
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import ExistingPageBot
from datetime import datetime
import asyncio
import aiohttp

REQ_HEADERS = {'User-Agent': 'atl.wiki/User:Hamachitan', 'From': 'mado@fyralabs.com'}
DEAD_LINK_TEMPLATE = 'Dead Link'

class LinkDetectorBot(ExistingPageBot):
    update_options = {
        'summary': '🍣 Detect and tag dead external links'
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
        # day = page.latest_revision.timestamp.strftime('%Y-%m-%d')
        day = datetime.now().strftime('%Y-%m-%d')
        wikicode = asyncio.run(self.process_wikicode(day, mw.parse(page.text)))
        self.put_current(str(wikicode), summary=self.opt.summary)

    async def check_head(self, url: str):
        try:
            async with self.session.head(url, allow_redirects=True, timeout=8) as resp:
                if resp.ok:
                    return 200
                return resp.status
        except Exception as e:
            return e

    async def check_get(self, url: str):
        try:
            async with self.session.get(url, allow_redirects=True, timeout=8) as resp:
                if resp.ok:
                    return 200
                return resp.status
        except Exception as e:
            return e

    async def process_wikicode(self, day: str, wikicode: mw.wikicode.Wikicode) -> mw.wikicode.Wikicode:
        self.session = aiohttp.ClientSession(headers=REQ_HEADERS)
        tasks = []
        nodes = []
        urls = []
        for node in wikicode.ifilter_external_links(recursive=True):
            url = str(node.url)
            print(f'... : {url}')
            tasks.append(asyncio.create_task(self.check_head(url)))
            nodes.append(node)
            urls.append(url)

        # Wait for each task individually and update the status line
        finished = [False] * len(tasks)
        status_codes = [None] * len(tasks)
        head_fails = [False] * len(tasks)
        while not all(finished):
            for i, task in enumerate(tasks):
                if finished[i] or not task.done():
                    continue
                status_code = task.result()
                status_codes[i] = status_code
                print(end=f'\033[{len(tasks)-i}A')
                print(end='\r' + ' ' * 80 + '\r')
                if status_code is not None and status_code != 200:
                    if head_fails[i]:
                        finished[i] = True
                        if not isinstance(status_code, int):
                            print(f'ERR!: {urls[i]}')
                        else:
                            print(f'{status_code} : {urls[i]}')
                    else:
                        if not isinstance(status_code, int):
                            status_code = 'ERR'
                        print(f'{status_code}?: {urls[i]}')
                        tasks[i] = asyncio.create_task(self.check_get(urls[i]))
                        head_fails[i] = True
                else:
                    finished[i] = True
                    print(f' OK : {urls[i]}')
                # Move cursor back down to the end
                print(end=f'\033[{len(tasks)-i-1}B')
            await asyncio.sleep(0.25)

        print()

        for i, url in enumerate(urls):
            if template := self.detect_dead_link_template(wikicode, nodes[i]):
                if template.params[1] == status_codes[i]:
                    continue
                wikicode.remove(template)

            if status_codes[i] != 200 and self.determine_mark_dead(wikicode, url, nodes[i], str(status_codes[i])):
                wikicode.insert_after(nodes[i], self.make_dead_link_template(day, str(status_codes[i])))

        await self.session.close()

        return wikicode

    @staticmethod
    def detect_dead_link_template(wikicode: mw.wikicode.Wikicode, node: mw.nodes.Node) -> mw.nodes.Template | None:
        # Remove dead link template if it exists right after the node
        parent = wikicode.get_parent(node)
        if parent:
            is_next = False
            for child in parent.__children__():
                if is_next:
                    break
                is_next = child == node
            else:
                return None
            if isinstance(child, mw.nodes.Template) and child.name == DEAD_LINK_TEMPLATE:
                return child
            return None

        idx = wikicode.index(node)
        if idx + 1 < len(wikicode.nodes):
            next_node = wikicode.nodes[idx + 1]
            if isinstance(next_node, mw.nodes.Template) and next_node.name == DEAD_LINK_TEMPLATE:
                return next_node
        return None

    def make_dead_link_template(self, day: str, reason: str):
        return mw.parse(f'{{{{{DEAD_LINK_TEMPLATE}|{day}|{reason}}}}}')

    @staticmethod
    def determine_mark_dead(wikicode: mw.wikicode.Wikicode, url: str, node: mw.nodes.Node, status) -> bool:
        ancestors = wikicode.get_ancestors(node)
        if not len(ancestors):
            return True
        print(f"==> {url}")
        print(f" Status : {status}")
        print()
        print(ancestors[0])
        print()
        return input("Mark as dead? (Y/n): ").lower().strip() in ['y', '']

def main(*args: str) -> None:
    """Parse command line arguments and invoke bot."""
    options = {}
    gen_factory = pagegenerators.GeneratorFactory()
    local_args = pywikibot.handle_args(args)
    local_args = gen_factory.handle_args(local_args)
    for arg in local_args:
        opt, sep, value = arg.partition(':')
        if opt in ('-summary'):
            options[opt[1:]] = value
    LinkDetectorBot(generator=gen_factory.getCombinedGenerator(), **options).run()

if __name__ == '__main__':
    main()
