__author__ = 'rycus'

import os
import subtitles

try:
    import babelfish
    import subliminal
except ImportError:
    pass  # no subliminal

class SubliminalProvider(subtitles.SubtitleProvider):

    def __init__(self, subliminal_provider):
        self._subliminal_provider = subliminal_provider
        self._subliminal_languages = { babelfish.Language('eng'), babelfish.Language('hun') } # TODO: fixed languages

    def query(self, query):
        guess = query.guess()
        if guess:
            video = subliminal.Video.fromguess(query.text, guess)
            with self._subliminal_provider:
                for subliminal_result in self._subliminal_provider.list_subtitles(video, self._subliminal_languages):
                    item = self._create_from_subliminal_subtitle(subliminal_result)
                    if not isinstance(item.language, str):
                        item.language = str(item.language)
                    score = 'Score: ' + str( subliminal_result.compute_score(video) )
                    if item.extras:
                        item.extras += ' (' + score + ')'
                    else:
                        item.extras = score
                    item.subliminal_filename = self._create_filename(query.text, item.language)
                    item.subliminal_result = subliminal_result
                    yield item

    def _create_filename(self, filename, language):
        pname = self.name().lower()
        base, ext = os.path.splitext(filename)
        return base + '.' + pname + '.' + language.lower() + '.srt'

    def _create_from_subliminal_subtitle(self, sub):
        pass

    def _do_download(self, cached, directory, timeout, fallback_name):
        try:
            filename = cached.subliminal_filename
            if filename is None or len(filename) == 0:
                filename = fallback_name

            with self._subliminal_provider:
                subtitle_content = self._subliminal_provider.download_subtitle(cached.subliminal_result)

            path = os.path.join(directory, filename)

            with open(path, 'w') as fout:
                fout.write(subtitle_content.encode('utf-8'))

            return path
        except Exception as ex:
            print 'Failed to download a subtitle using', self._subliminal_provider, '|', ex
