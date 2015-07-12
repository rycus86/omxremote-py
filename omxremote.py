"""
RaspberryPi::omxplayer Remote for Android

Wrapper for omxplayer on Raspberry Pi for starting videos 
and controlling playback, plus serving the Android client.

Created on Oct 1, 2013

@author: viktor.adam
"""

# TODO: settings for cli args
import util

import os
import uuid
import signal
import sys
import threading
import time

# default multicast communication parameters
MCAST_GRP = '224.1.1.7'
MCAST_PORT = 42002

# Android message identifiers
MSG_A_LOGIN             = 0xA1
MSG_A_LIST_FILES        = 0xA2
MSG_A_START_VIDEO       = 0xA3
MSG_A_STOP_VIDEO        = 0xA4
MSG_A_SET_VOLUME        = 0xA5
MSG_A_SEEK_TO           = 0xA6
MSG_A_PAUSE             = 0xA7
MSG_A_SPEED_INC         = 0xA8
MSG_A_SPEED_DEC         = 0xA9
MSG_A_SUB_DELAY_INC     = 0xAA
MSG_A_SUB_DELAY_DEC     = 0xAB
MSG_A_SUB_TOGGLE        = 0xAC
MSG_A_PLAYER_STATE      = 0xD1
MSG_A_PLAYER_PARAMS     = 0xD2
MSG_A_PLAYER_INFO       = 0xD3
MSG_A_PLAYER_EXTRA      = 0xD4
MSG_A_KEEPALIVE         = 0xE0
MSG_A_LIST_SETTINGS     = 0xE1
MSG_A_SET_SETTING       = 0xE2
MSG_A_QUERY_SUBTITLES   = 0xE3 # TODO: Only for TV Shows for now
MSG_A_DOWNLOAD_SUBTITLE = 0xE4
MSG_A_ERROR             = 0xF0
MSG_A_EXIT              = 0xFE

MSG_A_ERROR_INVALID_SESSION = 0xF1

# secret keyword for (a very basic) authentication
secret_keypass      = 'RPi::omxremote'
# max socket buffer size ( = max message length )
max_message_length  = 1500

# TODO: this doesn't get updated in util.* modules 
# so they all see it False even if --debug was specified
DEBUG = False

def is_debug():
    return DEBUG

class Availability(object):
    def __init__(self):
        self.guessit_available     = False

availability = Availability()

class Defaults(object):
    def __init__(self):
        self.path = os.path.expanduser('~')

defaults = Defaults()

# pip install guessit
def load_guessit(avl):
    try:
        if is_debug(): print 'Loading guessit module ...'
        import guessit  # @UnusedImport -- we are using this on another thread
        if is_debug(): print 'Module loaded: guessit'
        avl.guessit_available = True
    except ImportError:
        if is_debug(): print 'guessit module not available'

# TODO: use IMDbPY for movies (and shows?)

# session class
class __Session(object):
    id      = None
    socket  = None
    address = None
    player  = None
    video   = None
    info    = None
    info_parsed     = False
    extra   = None
    extra_parsed    = False
    drop_position_0 = False
    
    # clear session parameters
    def clear(self):
        self.id      = None
        self.socket  = None
        self.address = None
    
    def clear_player(self):
        self.player  = None
        self.video   = None
        self.info    = None
        self.info_parsed     = False
        self.extra   = None
        self.extra_parsed    = False
        self.drop_position_0 = False
    
# the current Android client session
session = __Session()

def check_session(socket, sender, data):
    sid = data[0:36]
    if sid == session.id:
        return (True, sid, data[36:])
    else:
        if is_debug(): print 'Sending invalid session to', sender
        socket.send(MSG_A_ERROR_INVALID_SESSION, None, destination=sender)
        return (False, None, None)

def do_player_poll():
    if session.address is None:
        return
    
    position, volume, paused = session.player.get_state()
    
    if position == 0 and session.drop_position_0:
        return
    
    # got a valid position
    session.drop_position_0 = False
    
    session.player.position = position
    session.player.volume   = volume / 100
    session.player.paused   = paused
    
    data  = ''
    data += 'p' + str(session.player.position)
    data += 'v' + str(session.player.volume)
    data += 'P' if paused else 'R'
    
    try:
        session.socket.send(MSG_A_PLAYER_STATE, data, destination=session.address)
        time.sleep(1)
    except:
        print 'Failed to send player state to', session.address

def player_polling():
    while( session.player is not None and session.player.is_valid() ):
        do_player_poll()
    
    # player exited
    session.socket.send(MSG_A_STOP_VIDEO, None, destination=session.address)
    session.clear_player()
    if is_debug(): print 'Player exited'

def guess_for_file(filename):
    import guessit # this should be fast since it is pre-loaded here
    
    if is_debug(): print 'Processing guessit info for', filename
    
    guess = guessit.guess_video_info(filename)
    if is_debug(): print 'Guessit response:', guess.nice_string()
    
    return guess

def process_player_info():
    if session.info_parsed or not availability.guessit_available:
        session.socket.send(MSG_A_PLAYER_INFO, session.info, destination=session.address)
        
        if session.extra_parsed:
            session.socket.send(MSG_A_PLAYER_EXTRA, session.extra, destination=session.address)
        # if session.extra is not parsed then there is no extra or it is still in construction
        
        return
    
    guess = guess_for_file(session.video)
    
    if 'type' in guess.keys():
        ftype = guess['type']

        if ftype == 'episode':
            if 'series' not in guess.keys():
                session.info_parsed = True
                return
                
            show = util.camelcase(guess['series'])
            
            season = None
            if 'season' in guess.keys():
                season = guess['season']
            
            episode = None
            if 'episodeNumber' in guess.keys():
                episode = guess['episodeNumber']
            
            data = 'SHOW$' + show + '$'
            if season:
                data += 'S' + str(season)
            if episode:
                data += 'E' + str(episode)
                
            session.info = data
            
            if show and season and episode:
                extra_thread = threading.Thread(name='PlayerExtra|Episode', \
                                target=process_episode_info, args=(show, season, episode))
                extra_thread.setDaemon(True)
                extra_thread.start()
        
        elif ftype == 'movie':
            if 'title' not in guess.keys():
                session.info_parsed = True
                return
            
            title = util.camelcase(guess['title'])
                
            year = None
            if 'year' in guess.keys():
                year = guess['year']
            
            data = 'MOVIE$' + title + '$'
            if year:
                data += 'Y' + str(year)
                
            session.info = data
                
        else:
            session.info_parsed = True
            return
    
    session.info = session.info.encode('ascii', 'ignore')
    session.info_parsed = True
    
    session.socket.send(MSG_A_PLAYER_INFO, session.info, destination=session.address)

# get extra data from theTVDB
def process_episode_info(series, season, episode):
    sd, ed = util.tvdb.parse_tvdb_info(series, season, episode)
    infos = []
    
    # series data
    if 'title'  in sd:  infos.append('ST:' + sd['title'])
    if 'imdb'   in sd:  infos.append('SI:' + sd['imdb'])
    if 'poster' in sd:  infos.append('SP:' + sd['poster'])
    
    # episode data
    if 'title'  in ed:  infos.append('ET:' + ed['title'])
    if 'date'   in ed:  infos.append('ED:' + ed['date'])
    if 'rating' in ed:  infos.append('ER:' + ed['rating'])
    if 'imdb'   in ed:  infos.append('EI:' + ed['imdb'])
    if 'poster' in ed:  infos.append('EP:' + ed['poster'])
    
    msg = '|'.join(infos)
    
    session.extra = msg.encode('ascii', 'ignore')
    session.extra_parsed = True
    
    session.socket.send(MSG_A_PLAYER_EXTRA, session.extra, destination=session.address)

# receiver implementation for Android clients
def my_handler(sock, sender, header, data):
    if is_debug(): print 'Received:', hex(header), data, '| From:', sender
    
    if header == MSG_A_LOGIN:
        if data == secret_keypass:
            sid = str( uuid.uuid4() )
            
            session.id      = sid
            session.socket  = sock
            session.address = sender
            
            if is_debug(): print 'Current session:', sid
            
            # send back a unicast message
            sock.send(header, sid + ' (' + str( sock.get_buffer_size() ) + ')', destination=sender)
            
            if session.player:
                msg  = 'd' + str( session.player.duration ) + 'v' + str( session.player.volume )
                msg += '|' + session.video
                sock.send(MSG_A_START_VIDEO, msg, destination=sender) 
                
                info = threading.Thread(target=process_player_info, name='PlayerInfo')
                info.start()
    
    elif header == MSG_A_EXIT:
        valid, sid, data = check_session(sock, sender, data)
        if valid:
            session.clear()
            if is_debug(): print 'Current session exited'
    
    elif header == MSG_A_KEEPALIVE:
        valid, sid, data = check_session(sock, sender, data)
        if valid:
            sock.send(MSG_A_KEEPALIVE, None, destination=sender)
                
    elif header == MSG_A_LIST_FILES:
        valid, sid, directory = check_session(sock, sender, data)
        if valid:
            if not directory:
                directory = defaults.path
            
            flist = util.create_file_list(directory)
            sock.send(MSG_A_LIST_FILES, flist, destination=sender)
    
    elif header == MSG_A_START_VIDEO:
        valid, sid, data = check_session(sock, sender, data)
        if valid:
            if '|' in data:
                video, subtitle = data.split('|')
            else:
                video, subtitle = data, None
            
            if not os.path.exists(video):
                sock.send(MSG_A_ERROR, 'Video file not found: ' + video, destination=sender)
                return
            
            if subtitle and not os.path.exists(subtitle):
                sock.send(MSG_A_ERROR, 'Subtitle file not found: ' + video, destination=sender)
                return
            
            commands = [ 'omxplayer' ]
            
            # settings
            for (key, desc, values, default, stype, scale) in util.Settings.all:  # @UnusedVariable
                value = util.Settings.get(key)
                if stype == 'SWITCH':
                    if value:
                        commands.append( '--' + key )
                else:
                    if stype == 'TEXT':
                        for v in value.split():
                            commands.append(v)
                    else:
                        commands.append( '--' + key )
                        commands.append(value)
                
            # subtitle
            if subtitle:
                commands.append( '--subtitles=' + subtitle )
                
            # and the video
            commands.append( video )
            
            try:
                if session.player:
                    session.player.exit()
                
                player = util.PlayerProcess(commands)
                duration, volume = player.init()
                if is_debug(): print 'Player started'
                
                session.video  = os.path.basename(video)
                session.info   = session.video
                session.extra  = None
                session.info_parsed  = False
                session.extra_parsed = False
                
                session.player = player
                session.player.duration = duration
                session.player.volume   = volume / 100
                
                data  = 'd' + str(session.player.duration) + 'v' + str(session.player.volume)
                data += '|' + session.video
                sock.send(MSG_A_START_VIDEO, data, destination=sender)
                
                polling = threading.Thread(target=player_polling, name='PlayerPolling')
                polling.start()
                
                info = threading.Thread(target=process_player_info, name='PlayerInfo')
                info.start()
                
            except Exception as ex:
                # TODO: the thread does not stop on exceptions
                print 'Failed to start video', video, ex
                sock.send(MSG_A_ERROR, 'Failed to start video: ' + str(ex), destination=sender)
                
    elif header == MSG_A_STOP_VIDEO:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            session.player.exit()
            
    elif header == MSG_A_PLAYER_PARAMS:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            msg  = 'd' + str( session.player.duration ) + 'v' + str( session.player.volume )
            msg += '|' + session.video
            sock.send(MSG_A_PLAYER_PARAMS, msg, destination=sender) 
    
    elif header == MSG_A_SET_VOLUME:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            volume = int(data) * 100
            session.player.set_volume( volume )
                
    elif header == MSG_A_SEEK_TO:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            position = int(data)
            session.player.seek_to( position / 1000 )
            # the player send position 0 while seeking
            session.drop_position_0 = True 
            
    elif header == MSG_A_PAUSE:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            session.player.pause()
            time.sleep(0.05)
            do_player_poll()
            
    elif header == MSG_A_SPEED_INC:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            session.player.increase_speed()
            time.sleep(0.05)
            do_player_poll()
            
    elif header == MSG_A_SPEED_DEC:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            session.player.decrease_speed()
            time.sleep(0.05)
            do_player_poll()
            
    elif header == MSG_A_SUB_DELAY_INC:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            session.player.increase_subtitle_delay()
            time.sleep(0.05)
            do_player_poll()
            
    elif header == MSG_A_SUB_DELAY_DEC:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            session.player.decrease_subtitle_delay()
            time.sleep(0.05)
            do_player_poll()
            
    elif header == MSG_A_SUB_TOGGLE:
        valid, sid, data = check_session(sock, sender, data)
        if valid and session.player:
            session.player.toggle_subtitle_visibility()
            time.sleep(0.05)
            do_player_poll()
    
    elif header == MSG_A_LIST_SETTINGS:
        valid, sid, data = check_session(sock, sender, data)
        if valid:
            msg = ''
            for (key, desc, values, default, stype, scale) in util.Settings.all:  # @UnusedVariable
                value = util.Settings.get(key)
                if stype == 'SWITCH':
                    value = ('1' if value is not None and value else '0')
                if stype == 'NUMBER':
                    value = str( int(value) / scale )
                
                msg += key + ';' + value + ';' + desc + ';' + \
                        (values if values is not None else '') + ';' + stype + ';' 
                
            if len(msg):
                msg = msg[0:-1]
                sock.send(MSG_A_LIST_SETTINGS, msg, destination=sender)
    
    elif header == MSG_A_SET_SETTING:
        valid, sid, data = check_session(sock, sender, data)
        if valid:
            key, value = data.split('=', 1)
            if len(value):
                stype = util.Settings.type_of(key)
                if stype == 'SWITCH':
                    value = '1' == value
                elif stype == 'NUMBER':
                    scale = util.Settings.scale_of(key)
                    value = str( int(value) * scale )
                util.Settings.set(key, value)
            else:
                util.Settings.set(key, None)
                
    elif header == MSG_A_QUERY_SUBTITLES:
        valid, sid, data = check_session(sock, sender, data)
        if valid:
            if len(data) > 2 and 'c$' == data[0:2]:
                query = data[ 2 : data.find('$', 2) ]
                info = data[ data.find('$', 2) + 1 : ]
                season, episode = [int(x) for x in info.split('x')]

                query_object = util.SubtitleQuery(query)
                query_object.season = season
                query_object.episode = episode
            else:
                query_object = util.SubtitleQuery(data)
                query_object.set_is_a_filename()
                query_object.guess_season_and_episode()

                if query_object.season is None or query_object.episode is None:
                    print 'File does not appear to be an episode of a TV show'
                    sock.send(MSG_A_ERROR, 'File does not appear to be an episode of a TV show', destination=sender)
                    return

            util.Subtitles.Cache.clear()

            providers = util.Subtitles.providers()
            for provider in providers:

                def do_query(provider, query_object, socket, sender):
                    try:
                        for item in provider.query(query_object):
                            util.Subtitles.Cache.add(provider, item)
                            socket.send(MSG_A_QUERY_SUBTITLES, item.to_string(), destination=sender)
                    except Exception as ex:
                        print 'Failed to look for an episode of', query_object.text, 'on', provider.name(), '|', ex

                th_query = threading.Thread(
                    target=do_query, args=(provider, query_object, sock, sender),
                    name='Query|' + provider.name())
                th_query.setDaemon(True)
                th_query.start()

            '''
            results = {}
            latch = util.CountdownLatch( len(providers) )

            for provider in providers:
                results[provider] = []
                
                def do_query(provider, query_object, results, latch):
                    try:
                        for item in provider.query(query_object):
                            results[provider].append(item) # SubtitleObject
                    except Exception as ex:
                        print 'Failed to look for an episode of', query_object.text, 'on', provider.name(), '|', ex

                    latch.countdown()

                th_query = threading.Thread(
                                target=do_query, args=(provider, query_object, results, latch),
                                name='Query|' + provider.name())
                th_query.setDaemon(True)
                th_query.start()

            latch.await(30)

            util.Subtitles.Cache.set(results)
            
            if is_debug(): print 'Subtitle results:'
            slist = []
            for provider in results:
                if is_debug(): print '---', provider.name(), '---'
                for res in results[provider]:
                    string = res.to_string()
                    slist.append(string)
                    if is_debug(): print '\t', string
                    
            response = '$'.join(slist)
            
            sock.send(MSG_A_QUERY_SUBTITLES, response, destination=sender)
            '''
    
    elif header == MSG_A_DOWNLOAD_SUBTITLE:
        valid, sid, data = check_session(sock, sender, data)
        if valid:
            pname, id, directory = data.split(';')
            if is_debug(): print 'Trying to download subtitle from', pname
            provider = util.Subtitles.provider_by_name(pname)
            if provider:
                dl = provider.download(id, directory)
                if dl is None: dl = ''
                sock.send(MSG_A_DOWNLOAD_SUBTITLE, dl, destination=sender)
            else:
                if is_debug(): print 'Failed to download subtitle, provider not found:', pname
                sock.send(MSG_A_ERROR, 'Failed to download subtitle, provider not found: ' + str(pname), destination=sender)


def wait_for_exit_signal():
    def handle_usr1(num, frame):
        pass
    
    signal.signal(signal.SIGUSR1, handle_usr1)
    signal.pause()
                
if __name__ == '__main__':
    if len(sys.argv) > 1:
        for idx in xrange(1, len(sys.argv)):
            if sys.argv[idx] == '--debug':
                DEBUG = True
            elif sys.argv[idx] == '--root':
                if len(sys.argv) > idx+1:
                    defaults.path = sys.argv[idx+1]
                else:
                    print '--root needs a path after it'

    # pre-load some modules
    threading.Thread(target=load_guessit, name='guessit|Loader', args=(availability,)).start()

    client = util.start_client(defaults.path, MCAST_GRP, MCAST_PORT)

    try:
        # raw_input('Press ENTER to exit\n')
        wait_for_exit_signal()
    except KeyboardInterrupt:
        print 'Keyboard interrupt received, stopping now'
    
    client.shutdown()
