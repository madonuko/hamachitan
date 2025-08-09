import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import ExistingPageBot
import mwparserfromhell


class TidyUpHeadingsBot(ExistingPageBot):
    update_options = {
        # 'text': 'text to update',
        "summary": "Remove redundant first heading"
    }

    def treat_page(self):
        page = self.current_page
        if not page.exists():
            print(f"[[{page.title()}]] does not exist")
            return
        if not page.has_permission():
            print(f"[[{page.title()}]] no perms")
            return
        wikicode = mwparserfromhell.parse(page.text)
        heading_title = None
        for heading in wikicode.ifilter_headings(
            False,
            lambda heading: heading.title.strip()
            in [page.title().strip(), "Introduction"],
        ):
            heading_title = heading.title
            i = wikicode.index(heading)
            next = wikicode.get(i + 1)
            while next.startswith("\n"):
                next = next[1:]
            wikicode.set(i + 1, next)
            wikicode.remove(heading)

        headings = wikicode.filter_headings()
        while len(headings) and all(h.level > 2 for h in headings):
            for h in headings:
                h.level -= 1

        if heading_title:
            self.put_current(
                str(wikicode),
                summary=f"/* {heading_title.strip()} */ 🍣 {self.opt.summary}",
            )
        else:
            self.put_current(str(wikicode), summary=f"🍣 Tidy up heading levels")


def main(*args: str) -> None:
    """Parse command line arguments and invoke bot."""
    options = {}
    gen_factory = pagegenerators.GeneratorFactory()
    # Option parsing
    local_args = pywikibot.handle_args(args)  # global options
    local_args = gen_factory.handle_args(local_args)  # generators options
    for arg in local_args:
        opt, sep, value = arg.partition(":")
        if opt in ("-summary"):
            options[opt[1:]] = value
    TidyUpHeadingsBot(generator=gen_factory.getCombinedGenerator(), **options).run()


if __name__ == "__main__":
    main()
