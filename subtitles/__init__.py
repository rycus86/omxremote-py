'''
Created on May 5, 2014

@author: rycus
'''

import os
import re
import threading
import urllib2
import util

class SubtitleQuery(object):

    def __init__(self, text):
        self.text = text
        self.season = None
        self.episode = None

        self.__is_a_filename = False
        self.__cached_guess = None

    def set_is_a_filename(self):
        self.__is_a_filename = True

    def guess_season_and_episode(self):
        guess = self.guess()
        if 'type' in guess and guess['type'] == 'episode':
            if 'season' in guess:
                self.season = guess['season']
            if 'episodeNumber' in guess:
                self.episode = guess['episodeNumber']

    def guess(self):
        if self.__is_a_filename:
            if self.__cached_guess is None:
                import guessit
                self.__cached_guess = guessit.guess_episode_info(self.text)
            return self.__cached_guess


class _SubtitleIdGenerator(object):

    def __init__(self):
        self.__value = 0
        self.__lock = threading.Lock()

    def next(self):
        with self.__lock:
            self.__value += 1
            return self.__value

class SubtitleObject(object):

    __ID_GENERATOR = _SubtitleIdGenerator()

    # TODO: remove url
    def __init__(self, provider, title, url, language='Unknown', extras=''):
        if url is not None:
            raise Exception('Parameter "url" is now deprecated')

        self.id = SubtitleObject.__ID_GENERATOR.next()
        self.provider = provider.name()
        self.title = title
        self.url = str(self.id) # TODO remove: url
        self.language = language
        self.extras = extras
    
    def to_string(self):
        string = self.provider
        string = string + ';' + self.__safe_title()
        string = string + ';' + self.url
        string = string + ';' + self.language
        string += ';'
        if self.extras and len(self.extras):
            string += self.extras.replace(';', '_')
        string = string.replace('$', '_')
        return string
    
    def __safe_title(self):
        safe = self.title.replace(';', ' ')
        try:
            return safe.encode('ascii', 'ignore')
        except:
            pass
        
        try:
            return safe.decode('utf-8').encode('ascii', 'ignore')
        except:
            pass

        return re.sub('[^a-zA-Z0-9\\-_\\.\\s]', '', safe)
    
    def __str__(self):
        # TODO: use id instead of url
        string = '[' + self.provider + ']'
        string = string + ' ' + self.title
        string = string + ' (' + self.language + ')'
        string = string + ' ' + self.url
        if self.extras and len(self.extras):
            string = string + ' | ' + self.extras
        
        return string

    def __repr__(self):
        return 'SubtitleObject #' + str(self.id)


class SubtitleQueryResults(object):

    def __init__(self):
        self.items = {}

    def get(self, provider, id):
        if provider in self.items:
            for item in self.items[provider]:
                if item.id == id:
                    return item

    def set(self, items):
        self.items = items

    def clear(self):
        self.items = {}

    def add(self, provider, item):
        if provider not in self.items:
            self.items[provider] = []

        self.items[provider].append(item)


class SubtitleProvider(object):
    
    __registered_providers = []

    Cache = SubtitleQueryResults()
    
    def name(self):
        return str(type(self).__name__)
    
    def query(self, query):
        raise Exception('Provider [' + str(type(self)) + '] provided no query option')
    
    def create(self, title, url, language='Unknown', extras=''):
        """ Creates a SubtitleObject for the current provider """
        return SubtitleObject(self, title, url, language, extras)
    
    def _recode_files_to_utf8(self):
        """ Return True, if files need recoding after download """
        return False

    @classmethod
    def __recode_file(cls, source):
        import util
        util.recode_file(source)

    @classmethod
    def _download_by_url(cls, url, directory, timeout=30, fallback_name='subtitle.srt'):
        # default implementation: download using the content-disposition when available
        try:
            request = urllib2.urlopen(url, timeout=timeout)
            filename = fallback_name
            header_name = 'Content-Disposition'
            if header_name in request.headers:
                cd = request.headers[header_name]
                if 'attachment' in cd.lower():
                    filename = cd.split('=', 1)[1].strip('"')

            content = request.read()

            path = os.path.join(directory, filename)

            with open(path, 'w') as fout:
                fout.write(content)

            request.close()

            return path
        except:
            return None

    def _do_download(self, cached, directory, timeout, fallback_name):
        print 'Provider [' + str(type(self)) + '] provided no download option'

    def download(self, id, directory, timeout=30, fallback_name='subtitle.srt'):
        cached = SubtitleProvider.Cache.get(self, int(id))
        if cached is None:
            print 'Subtitle result object not found for id: ', id
            return None

        path = self._do_download(cached, directory, timeout, fallback_name)
        print 'Download path:', path
        if path is not None:
            if self._recode_files_to_utf8():
                print 'Recoding', path
                self.__recode_file(path)

            return os.path.basename(path)
    
    @classmethod
    def providers(cls):
        return SubtitleProvider.__registered_providers
    
    @classmethod
    def provider_by_name(cls, name):
        for p in SubtitleProvider.__registered_providers:
            if p.name() == name:
                return p
    
    @classmethod
    def register(cls):
        instance = cls()
        SubtitleProvider.__registered_providers.append(instance)
