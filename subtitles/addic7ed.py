from HTMLParser import HTMLParser
from httplib import HTTPConnection
import os
import re
import urllib

from subtitles import SubtitleProvider
import util


class _Addic7edHelper():
    ''' Class for accessing Addic7ed.com subtitles '''

    def __init__(self, title = None):
        self.__cookie = None

        if title:
            self.search_show(title)

    def cookie(self):
        return self.__cookie;

    def searchShow(self, title):
        return self.search_show(title)

    def search_show(self, query):
        _results = { }

        encoded = urllib.quote_plus(query)
        conn = HTTPConnection('www.addic7ed.com')
        try:
            conn.request('GET', '/search.php?search=' + encoded)
            rsp = conn.getresponse()

            if 200 <= rsp.status < 300:
                for key, value in rsp.getheaders():
                    if key.lower() == 'set-cookie':
                        self.__cookie = value

                parser = _Addic7edHelper.SearchListParser()

                data = rsp.read()
                parser.feed(data)

                _results = parser.get_result_list()
            else:
                print "Failed to get info for '%s':" % query, rsp.status, rsp.reason
        finally:
            conn.close()

        return _results

    def list_shows(self, filter_by=None):
        _results = { }

        conn = HTTPConnection('www.addic7ed.com')
        try:
            conn.request('GET', '/')
            rsp = conn.getresponse()

            if 200 <= rsp.status < 300:
                for key, value in rsp.getheaders():
                    if key.lower() == 'set-cookie':
                        self.__cookie = value

                parser = _Addic7edHelper.ShowIdParser()

                data = rsp.read()
                parser.feed(data)

                _results = parser.get_result_list()
            else:
                print "Failed to get show list info:", rsp.status, rsp.reason
        finally:
            conn.close()

        if filter_by:
            _filtered = {}

            _search = re.sub('[^0-9a-z\s]', ' ', filter_by.lower())
            _parts = _search.split(' ')
            print 'Filtering by', _search, '|', filter_by
            for key in sorted(_results.keys()):
                _sname = _results[key].lower()
                if _search in _sname:
                    _filtered[key] = _results[key]
                else:
                    _ok = True
                    for _part in _parts:
                        if _part not in _sname:
                            _ok = False
                            break
                    if _ok:
                        _filtered[key] = _results[key]

            _results = _filtered

        return _results

    def search_episode_by_show(self, show_link, season_num, episode_num):
        ''' Searching by show is FASTER than searching the episode page '''
        _results = { }

        conn = HTTPConnection('www.addic7ed.com')
        try:
            if show_link[0] != '/': show_link = '/' + show_link

            conn.request('GET', show_link)
            rsp = conn.getresponse()

            for key, value in rsp.getheaders():
                print 'Header:', key, '=', value

            if 200 <= rsp.status < 300:
                for key, value in rsp.getheaders():
                    if key.lower() == 'set-cookie':
                        self.__cookie = value

                parser = _Addic7edHelper.ShowEpisodeListParser(season_num, episode_num)

                data = rsp.read()
                data = data[data.find('<form name="multidl" action="/downloadmultiple.php" method="post">'):]
                data = data[:data.find('</form>') + len('</form>')]
                data = re.sub('(width=)([0-9]+")', '\\1"\\2', data.strip())

                parser.feed(data)

                _results = parser.get_result_list()
            else:
                print "Failed to get info at '%s':" % show_link, rsp.status, rsp.reason
        finally:
            conn.close()

        return _results

    def search_episode_by_show_id(self, show_id, season_num):
        ''' Searching by show id '''
        _results = { }

        conn = HTTPConnection('www.addic7ed.com')
        try:
            show_link = '/ajax_loadShow.php?show=' + str(show_id) + '&season=' + str(season_num) + '&langs=|1|'

            conn.request('GET', show_link)
            rsp = conn.getresponse()

            if 200 <= rsp.status < 300:
                for key, value in rsp.getheaders():
                    if key.lower() == 'set-cookie':
                        self.__cookie = value

                parser = _Addic7edHelper.ShowByIdEpisodeListParser(season_num)

                data = rsp.read()
                data = data[data.find('<form name="multidl" action="/downloadmultiple.php" method="post">'):]
                data = data[:data.find('</form>') + len('</form>')]
                data = re.sub('(width=)([0-9]+")', '\\1"\\2', data.strip())

                parser.feed(data)

                _results = parser.get_result_list()
            else:
                print "Failed to get info at '%s':" % show_link, rsp.status, rsp.reason
        finally:
            conn.close()

        return _results

    def search_episode_by_link(self, episode_link):
        ''' Searching the episode page is SLOWER than searching by show '''
        _results = { }

        conn = HTTPConnection('www.addic7ed.com')
        try:
            if episode_link[0] != '/': episode_link = '/' + episode_link

            conn.request('GET', episode_link)
            rsp = conn.getresponse()

            if 200 <= rsp.status < 300:
                for key, value in rsp.getheaders():
                    if key.lower() == 'set-cookie':
                        self.__cookie = value

                parser = _Addic7edHelper.ShowEpisodePageParser()

                data = rsp.read()

                # Fix <font color=red> and <font color='red'>
                data = re.sub('color=\'?([a-z]+)\'?', 'color="\\1"', data)
                # Fix value="true"/
                data = re.sub('(="[^"]+")/', '\\1', data)

                parser.feed(data)

                _results = parser.get_result_list()
            else:
                print "Failed to get info at '%s':" % episode_link, rsp.status, rsp.reason
        finally:
            conn.close()

        return _results

    class ShowIdParser(HTMLParser):
        def __init__(self):
            HTMLParser.__init__(self)

            self._result_list = {}

            self._in_select = False
            self._option_value = None
            self._option_data = ''

        def handle_starttag(self, tag, attrs):
            if tag.lower() == 'select':
                for key, value in attrs:
                    if key.lower() == 'name' and value.lower() == 'qsshow':
                        self._in_select = True
            elif self._in_select and tag.lower() == 'option':
                for key, value in attrs:
                    if key.lower() == 'value':
                        self._option_value = value

        def handle_endtag(self, tag):
            if tag.lower() == 'select':
                self._in_select = False
            elif self._in_select and tag.lower() == 'option':
                if self._option_value and self._option_data:
                    try:
                        _sid = int(self._option_value)
                        if _sid > 0:
                            self._result_list[_sid] = self._option_data
                    except:
                        pass
                self._option_value = None
                self._option_data = ''

        def handle_data(self, data):
            if self._in_select and self._option_value:
                self._option_data += data

        def get_result_list(self):
            return self._result_list

    class SearchListParser(HTMLParser):
        def __init__(self):
            HTMLParser.__init__(self)

            self.__found_show_link_item = False
            self.__found_television_td = False
            self.__found_link_a = False
            self.__result_list = { }
            self.__current_item = { }

        def handle_starttag(self, tag, attrs):
            if tag.lower() == 'img':
                for key, value in attrs:
                    if key.lower() == 'src':
                        if 'images/television.png' in value.lower():
                            self.__found_television_td = True
                        elif 'images/database.png' in value.lower():
                            self.__found_show_link_item = True
            elif tag.lower() == 'a':
                if self.__found_television_td: self.__found_link_a = True
                for key, value in attrs:
                    if key.lower() == 'href':
                        if 'serie/' == value.lower()[:6]:
                            self.__current_item['link'] = value
                            self.__current_item['directory'] = value[6:str(value).find('/', 6)]
                        elif '/show/' == value.lower()[:6] and self.__found_show_link_item:
                            _show_params = { }
                            _show_params['id'] = int(value.lower()[6:])
                            _show_params['link'] = value
                            self.__result_list['show'] = _show_params

        def handle_data(self, data):
            if self.__found_link_a:
                try:
                    self.__current_item['title'] = data

                    _number = re.sub('(.*)\s([0-9]{1,2}x[0-9]{1,2})\s(.*)', '\\2', data)
                    _season  = int( _number[ : _number.index('x')] )
                    _episode = int( _number[_number.index('x')+1 : ] )

                    _two_char = lambda x: ('0' + str(x)) if x < 10 else str(x)

                    self.__current_item['season']  = int(_season)
                    self.__current_item['episode'] = int(_episode)

                    self.__current_item['number'] = _two_char(_season) + 'x' + _two_char(_episode)
                except:
                    pass

        def handle_endtag(self, tag):
            if tag.lower() == 'tr':
                if self.__found_link_a and 'number' in self.__current_item:
                    _number = self.__current_item['number']
                    _directory = self.__current_item['directory']
                    self.__result_list[_directory + "_" + _number] = self.__current_item.copy()

                self.__found_television_td = False
                self.__found_link_a = False
                self.__current_item = { }
            elif tag.lower() == 'center':
                self.__found_show_link_item = False

        def get_result_list(self):
            return self.__result_list

    class ShowEpisodeListParser(HTMLParser):
        def __init__(self, season_num, episode_num):
            HTMLParser.__init__(self)

            self._season_num = season_num
            self._episode_num = episode_num
            self._result_list = { }

            self.__found_episode_table = False
            self.__found_title_link = False
            self.__found_episode_version = False
            self.__found_language_cell = False
            self.__found_english_row = False
            self.__found_download_img = False

            self.__current_version = None

        def handle_starttag(self, tag, attrs):
            if tag.lower() == 'a':
                if not self.__found_episode_table:
                    for key, value in attrs:
                        if key.lower() == 'href':
                            if ('/' + str(self._season_num) + '/' + str(self._episode_num) + '/') in value:
                                self.__found_episode_table = True
                                self.__found_title_link = True
                elif self.__found_english_row and self.__found_download_img:
                    for key, value in attrs:
                        if key.lower() == 'href':
                            self._result_list[value.strip()] = { }
                            self._result_list[value.strip()]['title'] = self.__current_version
            elif tag.lower() == 'td' and self.__found_episode_table:
                for key, value in attrs:
                    if key.lower() == 'class':
                        if value.lower() == 'language':
                            self.__found_language_cell = True
                        elif value.lower() == 'newsclaro':
                            self.__found_episode_version = True
            elif tag.lower() == 'img':
                for key, value in attrs:
                    if key.lower() == 'src' and value.lower() == '/images/download.png':
                        self.__found_download_img = True

        def handle_data(self, data):
            if self.__found_episode_table:
                if self.__found_episode_version:
                    _version = data.strip()
                    if _version:
                        self.__current_version = data.strip()
                elif self.__found_language_cell:
                    if 'English' == data.strip():
                        self.__found_english_row = True
                elif self.__found_title_link:
                    self._result_list['title'] = data.strip()

        def handle_endtag(self, tag):
            if tag.lower() == 'table':
                self.__found_episode_table = False
            elif tag.lower() == 'td':
                self.__found_episode_version = False
                self.__found_language_cell = False
                self.__found_download_img = False
            elif tag.lower() == 'tr':
                self.__found_english_row = False
            elif tag.lower() == 'a':
                self.__found_title_link = False

        def get_result_list(self):
            return self._result_list

    class ShowByIdEpisodeListParser(HTMLParser):
        def __init__(self, season_num):
            HTMLParser.__init__(self)

            self._season_num = season_num
            self._result_list = { }

            self._in_tr = False
            self._in_tr_td = False
            self._tr_cell_idx = 0

            self._data_season_num = ''
            self._data_episode_num = ''
            self._data_language = ''
            self._data_version = ''
            self._data_completed = ''
            self._data_link = ''

        def handle_starttag(self, tag, attrs):
            if tag.lower() == 'tr':
                self._in_tr = True
            elif self._in_tr and tag.lower() == 'td':
                self._in_tr_td = True
            elif self._in_tr_td and self._tr_cell_idx == 9 and tag.lower() == 'a':
                for key, value in attrs:
                    if key.lower() == 'href':
                        self._data_link = 'http://www.addic7ed.com' + value

        def handle_endtag(self, tag):
            if tag.lower() == 'tr':
                self._in_tr = False
                self._tr_cell_idx = 0

                try:
                    _parsed_num = int(self._data_season_num)
                    if _parsed_num == self._season_num and \
                        self._data_episode_num and self._data_completed.lower() == 'completed' and self._data_link:
                        _parsed_data = {}
                        _parsed_data['episode'] = int(self._data_episode_num)
                        _parsed_data['language'] = self._data_language
                        _parsed_data['version'] = self._data_version
                        self._result_list[self._data_link] = _parsed_data
                except:
                    pass

                self._data_season_num = ''
                self._data_episode_num = ''
                self._data_language = ''
                self._data_version = ''
                self._data_completed = ''
                self._data_link = ''
            elif tag.lower() == 'td':
                self._in_tr_td = False
                self._tr_cell_idx += 1

        def handle_data(self, data):
            if self._in_tr_td and self._tr_cell_idx == 0:
                self._data_season_num += data
            elif self._in_tr_td and self._tr_cell_idx == 1:
                self._data_episode_num += data
            elif self._in_tr_td and self._tr_cell_idx == 3:
                self._data_language += data
            elif self._in_tr_td and self._tr_cell_idx == 4:
                self._data_version += data
            elif self._in_tr_td and self._tr_cell_idx == 5:
                self._data_completed += data

        def get_result_list(self):
            return self._result_list

    class ShowEpisodePageParser(HTMLParser):
        def __init__(self):
            HTMLParser.__init__(self)

            self.__found_show_title_cell = False
            self.__found_title_cell = False
            self.__found_language_cell = False
            self.__found_english_row = False
            self.__found_alternative = False

            self.__range_alternative = 0

            self._current_title = None
            self._current_alternative = None
            self._current_link = None

            self._result_list = { }

        def handle_starttag(self, tag, attrs):
            if tag.lower() == 'td':
                for key, value in attrs:
                    if key.lower() == 'class':
                        if value == 'NewsTitle':
                            self.__found_title_cell = True
                            self.__range_alternative = 2
                        elif value == 'newsDate' and self.__range_alternative > 0:
                            self.__found_alternative = True
                            self.__range_alternative = 0
                        elif value == 'language':
                            self.__found_language_cell = True
            elif tag.lower() == 'a' and self.__found_english_row:
                for key, value in attrs:
                    if key.lower() == 'href':
                        self._current_link = value
            elif tag.lower() == 'span':
                for key, value in attrs:
                    if key.lower() == 'class' and value.lower() == 'titulo':
                        self.__found_show_title_cell = True

        def handle_data(self, data):
            if self.__found_title_cell:
                self._current_title = data.strip()
            elif self.__found_alternative:
                _alt = data.strip()
                if _alt:
                    self._current_alternative = data.strip()
            elif self.__found_language_cell:
                _lang = data.strip()
                if _lang:
                    if _lang == 'English':
                        self.__found_english_row = True
            elif self.__found_show_title_cell and 'title' not in self._result_list.keys():
                _title = data.strip()
                if _title:
                    self._result_list['title'] = _title

        def handle_endtag(self, tag):
            if tag.lower() == 'tr':
                self.__range_alternative -= 1
                if self.__found_english_row:
                    _params = { 'title': self._current_title }
                    if self._current_alternative: _params['alternative'] = self._current_alternative
                    self._result_list[self._current_link] = _params

                    self.__found_english_row = False
                    self._current_title = None
                    self._current_alternative = None
                    self._current_link = None
            elif tag.lower() == 'td':
                self.__found_alternative = False
                self.__found_title_cell = False
                self.__found_language_cell = False

        def get_result_list(self):
            return self._result_list


class Addic7ed(SubtitleProvider):

    __DOMAIN = 'www.addic7ed.com'
    __PREFIX = 'http://' + __DOMAIN

    def __init__(self):
        self.__helper = _Addic7edHelper()

    def _recode_files_to_utf8(self):
        return True

    def query(self, query):
        guess = query.guess()
        query.guess_season_and_episode()
        ns = query.season
        ne = query.episode
        query_text = util.camelcase(guess['series'])

        r_shows = self.__helper.search_show(query_text)
        matches = []

        for key in sorted(r_shows.keys()):
            val = r_shows[key]
            if 'season' in val.keys() and 'episode' in val.keys() and val['season'] == ns and val['episode'] == ne:
                matches.append(val)

        for match in matches:
            title = match['title']
            link = match['link']
            r_episode = self.__helper.search_episode_by_link(link)
            for url in r_episode:
                if url == 'title': continue
                fulltitle = title + ' (' + r_episode[url]['title'] + ')'
                extras = ''
                if 'alternative' in r_episode[url]:
                    extras = r_episode[url]['alternative']

                item = self.create(fulltitle, None, 'en', extras)
                item.temp_url = Addic7ed.__PREFIX + url
                yield item

    def __do_download(self, url, directory, filename, timeout, referer=None):
        conn = HTTPConnection('www.addic7ed.com', timeout=timeout)
        try:
            conn.request('GET', url, headers={'Cookie': self.__helper.cookie(), 'Referer': referer})
            rsp = conn.getresponse()

            if 200 <= rsp.status < 300:
                att = rsp.getheader('content-disposition', None)
                if att and 'filename=' in att:
                    filename = re.sub('attachment;\s+filename="(.*)"', '\\1', att)
                    pass

                data = rsp.read()

                filename = re.sub('[^a-zA-Z0-9.-]', '_', filename)

                path = os.path.join(directory, filename)

                with file(path, 'w') as sf:
                    sf.write(data)

                return path
            elif 300 <= rsp.status < 400:
                return self.__do_download(url, directory, filename, timeout, rsp.getheader('Location', None))
            else:
                print "Failed to download '%s':" % url, rsp.status, rsp.reason
        finally:
            conn.close()

    def _do_download(self, cached, directory, timeout, fallback_name):
        url = cached.temp_url
        url = url.replace('http://addic7ed.com', '')
        return self.__do_download(url, directory, fallback_name, timeout, None)

Addic7ed.register()
