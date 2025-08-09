import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import ExistingPageBot


class StripLeadingEmptyLinesBot(ExistingPageBot):
    update_options = {
        # 'text': 'text to update',
        "summary": "Strip leading empty lines"
    }

    def treat_page(self):
        page = self.current_page
        if not page.exists():
            print(f"[[{page.title()}]] does not exist")
            return
        if not page.has_permission():
            print(f"[[{page.title()}]] no perms")
            return
        text = ""
        i = 0
        while i < len(page.text):
            while page.text[i].isspace():
                i += 1
            if page.text[i : i + 2] != "{{":
                break
            text += "{{"
            i += 2
            while page.text[i : i + 2] != "}}":
                if page.text[i : i + 8] == "<nowiki>":
                    while page.text[i : i + 9] != "</nowiki>":
                        text += page.text[i]
                        i += 1
                text += page.text[i]
                i += 1
            text += "}}"
            i += 2
            continue
        text += page.text[i:]
        self.put_current(text, summary="🍣 Strip leading empty lines")


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
    StripLeadingEmptyLinesBot(
        generator=gen_factory.getCombinedGenerator(), **options
    ).run()


if __name__ == "__main__":
    main()
