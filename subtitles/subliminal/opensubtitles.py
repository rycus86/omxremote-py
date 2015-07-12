__author__ = 'rycus'

from subtitles.subliminal import SubliminalProvider

try:
    from subliminal.providers.opensubtitles import OpenSubtitlesProvider
except ImportError:
    pass  # no subliminal


class OpenSubtitles(SubliminalProvider):

    def __init__(self):
        SubliminalProvider.__init__(self, OpenSubtitlesProvider())

    def _create_from_subliminal_subtitle(self, sub):
        if sub.movie_release_name is not None:
            title = sub.movie_release_name
        else:
            title = sub.series_name
            title = title + ' / ' + sub.series_title
            title = title + ' ' + OpenSubtitles.__two_char(sub.series_season)
            title = title + 'x' + OpenSubtitles.__two_char(sub.series_episode)

        return self.create(title.strip(), None, sub.language, None)

    @classmethod
    def __two_char(cls, num):
        return str(num) if num < 10 else ('0' + str(num))

try:
    OpenSubtitles.register()
except:
    pass  # module won't be available
