'''
Created on May 5, 2014

@author: rycus
'''

from HTMLParser import HTMLParser
from httplib import HTTPConnection

import re
import urllib
try:
    import guessit
except ImportError:
    pass  # no guessit module

import util

from subtitles import SubtitleProvider

class SuperSubtitles(SubtitleProvider):
    
    __DOMAIN = 'www.feliratok.info'
    __PREFIX = 'http://' + __DOMAIN

    def _recode_files_to_utf8(self):
        return True
    
    def query(self, query):
        guess = query.guess()
        query.guess_season_and_episode()
        query_text = util.camelcase(guess['series'])

        for language, group, fname, link in self.search_show(query_text, query.season, query.episode):
            item = self.create(fname, None, language, group)
            item.temp_url = SuperSubtitles.__PREFIX + link
            yield item

    def _do_download(self, cached, directory, timeout, fallback_name):
        return SuperSubtitles._download_by_url(cached.temp_url, directory, timeout, fallback_name)

    def search_show(self, query, season, episode):
        encoded = urllib.quote_plus(query)
        conn = HTTPConnection(SuperSubtitles.__DOMAIN, timeout=30)
        try:
            conn.request('GET', '/?search=' + encoded)
            rsp = conn.getresponse()

            if 200 <= rsp.status < 300:
                parser = SuperSubtitles.SSParser()
                
                data = rsp.read()
                parser.feed(data)
                
                _results = parser.get_results()
                
                key = str(season) + '_' + str(episode)
                if key in _results:
                    return _results[key]
            else:
                print "Failed to get info for '%s':" % query, rsp.status, rsp.reason
        finally:
            conn.close()

        return []
            
    class SSParser(HTMLParser):
        
        def __init__(self):
            HTMLParser.__init__(self)
            
            self.__pattern = '\\/index\\.php\\?action=letolt\\&fnev=(.+\\.srt)\\&felirat=([0-9]+)'
            self.__results = { }
            
            self.__processing_language = False
            self.__language = 'unknown'
            
        def handle_starttag(self, tag, attrs):
            HTMLParser.handle_starttag(self, tag, attrs)
            
            if tag.lower() == 'a':
                for aname, avalue in attrs:
                    if 'href' == aname:
                        match = re.match(self.__pattern, avalue, re.IGNORECASE)
                        if match:
                            fname = match.group(1)
                            fid   = match.group(2)
                            link  = '/index.php?action=letolt&fnev=' + urllib.quote(fname) + '&felirat=' + fid
                            guess = guessit.guess_episode_info(fname)
                            if guess and 'season' in guess and 'episodeNumber' in guess:
                                season  = str( guess['season'] )
                                episode = str( guess['episodeNumber'] )
                                group   = 'UNKNOWN'
                                if 'releaseGroup' in guess:
                                    group = str( guess['releaseGroup'] )
                                
                                key = season + '_' + episode
                                item = (self.__language, group, fname, link)
                                
                                if key in self.__results:
                                    self.__results[key].append(item)
                                else:
                                    self.__results[key] = [ item ]
            elif tag.lower() == 'small':
                self.__processing_language = True
                            
        def handle_data(self, data):
            if self.__processing_language:
                if 'magyar' in data.lower():
                    self.__language = 'hu'
                elif 'angol' in data.lower():
                    self.__language = 'en'
        
        def handle_endtag(self, tag):
            if tag.lower() == 'small':
                self.__processing_language = False
        
        def get_results(self):
            return self.__results

SuperSubtitles.register()
