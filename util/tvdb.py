'''
Created on Nov 18, 2013

@author: rycus
'''

import omxremote

import xml.sax as sax
import urllib
import traceback

tvdb_api_key = '5EDB240BB69AA812'

base_api_url    = 'http://thetvdb.com/api/'
base_banner_url = 'http://thetvdb.com/banners/'
base_imdb_url   = 'http://www.imdb.com/title/'


class __CHandler(sax.ContentHandler):

    def __init__(self, data_map, end_element=None):
        sax.ContentHandler.__init__(self)
        self.current = None
        self.data_map = data_map
        self.data_map.clear()
        self.end_element = end_element
        self.finished = False
    
    def startElement(self, name, attrs):
        sax.ContentHandler.startElement(self, name, attrs)
        self.current = name
        
    def characters(self, content):
        if not self.finished:
            data = content.strip()
            if data:
                self.data_map[self.current] = data
    
    def endElement(self, name):
        if self.end_element and name == self.end_element:
            self.finished = True


def parse_tvdb_info(series, season, episode):
    parsed_data = { }
    
    get_series_api = base_api_url + 'GetSeries.php?seriesname=' + urllib.quote_plus(series)

    try:
        sax.parse(get_series_api, __CHandler(parsed_data, 'Series'))  # finish on first found entity
    except sax.SAXException:
        print 'Failed to parse initial TVDB data at %s' % get_series_api
        traceback.print_exc()
    
    if omxremote.is_debug():
        print 'TVDB| GetSeries data:'
        for k in parsed_data:
            print 'TVDB|     ', k, ':', parsed_data[k]
    
    series_data = { }
    
    if 'seriesid' not in parsed_data:
        return { }, { }
    
    seriesid = parsed_data['seriesid']
    series_data['id'] = seriesid
        
    get_series_api = base_api_url + tvdb_api_key + '/series/' + seriesid

    try:
        sax.parse(get_series_api, __CHandler(parsed_data))
    except sax.SAXException:
        print 'Failed to parse TVDB series data at %s' % get_series_api
        traceback.print_exc()
    
    if omxremote.is_debug():
        print 'TVDB| Series data:'
        for k in parsed_data:
            print 'TVDB|     ', k, ':', parsed_data[k]
    
    if 'SeriesName' in parsed_data:
        series_data['title'] = parsed_data['SeriesName']
    if 'IMDB_ID' in parsed_data:
        series_data['imdb'] = base_imdb_url + parsed_data['IMDB_ID']
    if 'poster' in parsed_data:
        series_data['poster'] = base_banner_url + parsed_data['poster']
    
    episode_data = { }
    
    get_episode_api = base_api_url + tvdb_api_key + '/series/' + seriesid + '/default/' + str(season) + '/' + str(episode)

    try:
        sax.parse(get_episode_api, __CHandler(parsed_data))
    except sax.SAXException:
        print 'Failed to parse TVDB episode data at %s' % get_episode_api
        traceback.print_exc()
    
    if omxremote.is_debug():
        print 'TVDB| Episode data:'
        for k in parsed_data:
            print 'TVDB|     ', k, ':', parsed_data[k]
    
    if 'EpisodeName' in parsed_data:
        episode_data['title'] = parsed_data['EpisodeName']
    if 'FirstAired' in parsed_data:
        episode_data['date'] = parsed_data['FirstAired']
    if 'IMDB_ID' in parsed_data:
        episode_data['imdb'] = base_imdb_url + parsed_data['IMDB_ID']
    if 'Rating' in parsed_data:
        episode_data['rating'] = parsed_data['Rating']
    if 'filename' in parsed_data:
        episode_data['poster'] = base_banner_url + parsed_data['filename']
    
    return series_data, episode_data
