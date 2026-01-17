from pywikibot import family


class Family(family.Family):
    name = "atlwiki"
    langs = {
        "en": "atl.wiki",
    }

    def scriptpath(self, code):
        return ""

    def protocol(self, code):
        return 'HTTPS'
