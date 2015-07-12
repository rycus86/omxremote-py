__author__ = 'rycus'

from subtitles.subliminal import SubliminalProvider
from subliminal.providers.addic7ed import Addic7edProvider


class _LocalCachingAddic7ed(Addic7edProvider):

    __cached_show_ids = None

    def get_show_ids(self):
        # cache region doesn't work for some reason,
        # so we use a different (very simple) cache,
        # and the original implementation from subliminal
        if _LocalCachingAddic7ed.__cached_show_ids is None:
            soup = self.get('/shows.php')
            show_ids = {}
            for html_show in soup.select('td.version > h3 > a[href^="/show/"]'):
                show_ids[html_show.string.lower()] = int(html_show['href'][6:])
            _LocalCachingAddic7ed.__cached_show_ids = show_ids
        return _LocalCachingAddic7ed.__cached_show_ids


class Addic7ed(SubliminalProvider):

    def __init__(self):
        SubliminalProvider.__init__(self, _LocalCachingAddic7ed())

    def _create_from_subliminal_subtitle(self, sub):
        title = sub.series + ' / ' + sub.title
        return self.create(title.strip(), None, sub.language, sub.version)

# not fully working Addic7ed.register()
