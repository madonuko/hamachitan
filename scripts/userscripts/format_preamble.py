import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import ExistingPageBot
import mwparserfromhell as mw

import re

RE_DUPLINES = re.compile(r'\n{3,}')


class FormatPreambleBot(ExistingPageBot):
    update_options = {
        # 'text': 'text to update',
        'summary': 'Format preamble'
    }

    def treat_page(self):
        page = self.current_page
        if not page.exists():
            print(f'[[{page.title()}]] does not exist')
            return
        if not page.has_permission():
            print(f'[[{page.title()}]] no perms')
            return
        text = ''
        wikicode = mw.parse(self.current_page.text)
        first_wikilink_index = -1
        i = 0
        while i < len(wikicode.nodes):
            node = wikicode.nodes[i]
            i += 1
            if isinstance(node, mw.nodes.Text):
                if node.value.isspace():
                    if text != '' and not text.endswith('\n'):
                        text += '\n'
                    continue
                if node.value[0].isspace() and text != '' and not text.endswith('\n'):
                    text += '\n'
                while node.value[0].isspace():
                    node.value = node.value[1:]
                text += node.value
                break
            if isinstance(node, mw.nodes.Template):
                if '\n' in str(node) and not text.endswith('\n') and text != '':
                    text += '\n' + str(node) + '\n'
                elif '\n' in str(node):
                    text += str(node) + '\n'
                elif len(str(node)) >= 80 and len(node.params) >= 2:
                    # try to make it multiline
                    if not text.endswith('\n') and text != '':
                        text += '\n'
                    text += '{{' + str(node.name).strip()
                    for param in node.params:
                        text += '\n|'
                        if param.showkey:
                            param.name = f' {param.name.strip()} '
                            param.value = ' ' + param.value.strip()
                        text += str(param)
                    text += '\n}}\n'
                else:
                    text += str(node)
                continue
            if isinstance(node, mw.nodes.Heading):
                while (
                    x := input(f'Remove heading `{node.title.strip()}`? ').lower()
                ) not in 'yn':
                    pass
                if x == 'y':
                    continue
                if not text.endswith('\n'):
                    text = '\n'
                text += str(node)
                continue
            if isinstance(node, mw.nodes.Wikilink):
                if first_wikilink_index == -1 or node.title.lower().startswith(
                    'category:'
                ):
                    first_wikilink_index = len(text)
                if ':' not in str(node) or str(node).lower().startswith('guides'):
                    text += str(node)
                    break
                else:
                    text += str(node) + '\n'
                continue
            text += str(node)
            break
        wikicode.nodes = wikicode.nodes[i:]
        # also move the categories to top
        wikilinks = wikicode.filter_wikilinks(
            matches=lambda wl: wl.title.lower().startswith('category:')
        )
        if len(wikilinks):
            if first_wikilink_index == -1:
                first_wikilink_index = 0
            text = (
                text[:first_wikilink_index]
                + '\n'.join(str(wl) for wl in wikilinks)
                + '\n'
                + text[first_wikilink_index:]
            )
        for wl in wikilinks:
            i = wikicode.index(wl)
            try:
                if isinstance(node := wikicode.get(i + 1), mw.nodes.Text):
                    node.value = node.value.removeprefix('\n')
            except IndexError:
                pass
            wikicode.remove(wl)

        text += str(wikicode)

        text = self.strip_dup_lines(text)

        self.put_current(text, summary=f'🍣 {self.opt.summary}')

    def strip_dup_lines(self, text: str) -> str:
        wikicode = mw.parse(text)
        for text in wikicode.ifilter_text(matches=lambda text: '\n\n\n' in text.value):
            text.value = RE_DUPLINES.sub('\n\n', text.value)
        return str(wikicode)


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
    FormatPreambleBot(generator=gen_factory.getCombinedGenerator(), **options).run()


if __name__ == '__main__':
    main()
