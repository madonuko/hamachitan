from pywikibot import family


class Family(family.Family):
    name = "fosswiki"
    langs = {
        "en": "foss.wiki",
    }

    def scriptpath(self, code):
        return ""

    def protocol(self, code):
        return 'HTTPS'
