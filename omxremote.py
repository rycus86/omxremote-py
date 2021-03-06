'''
RaspberryPi::omxplayer Remote for Android

Wrapper for omxplayer on Raspberry Pi for starting videos 
and controlling playback, plus serving the Android client.

Created on Oct 1, 2013

@author: viktor.adam
'''

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
MCAST_PORT = 42001

# Android message identifiers
MSG_A_LOGIN         = 0xA1
MSG_A_LIST_FILES    = 0xA2
MSG_A_START_VIDEO   = 0xA3
MSG_A_STOP_VIDEO    = 0xA4
MSG_A_SET_VOLUME    = 0xA5
MSG_A_SEEK_TO       = 0xA6
MSG_A_PAUSE         = 0xA7
MSG_A_SPEED_INC     = 0xA8
MSG_A_SPEED_DEC     = 0xA9
MSG_A_SUB_DELAY_INC = 0xAA
MSG_A_SUB_DELAY_DEC = 0xAB
MSG_A_SUB_TOGGLE    = 0xAC
MSG_A_PLAYER_STATE  = 0xD1
MSG_A_PLAYER_PARAMS = 0xD2
MSG_A_PLAYER_INFO   = 0xD3
MSG_A_PLAYER_EXTRA  = 0xD4
MSG_A_KEEPALIVE     = 0xE0
MSG_A_LIST_SETTINGS = 0xE1
MSG_A_SET_SETTING   = 0xE2
MSG_A_ERROR         = 0xF0
MSG_A_EXIT          = 0xFE

MSG_A_ERROR_INVALID_SESSION = 0xF1

# secret keyword for (a very basic) authentication
secret_keypass      = 'RPi::omxremote'
# default path for file listing
default_path        = os.path.expanduser('~')
# max socket buffer size ( = max message length )
max_message_length  = 1500

# TODO: this doesn't get updated in util.* modules 
# so they all see it False even if --debug was specified
DEBUG = False

class Availability(object):
    def __init__(self):
        self.guessit_available   = False
        self.subliminal_available  = False

availability = Availability()

# pip install guessit
def load_guessit(avl):
    try:
        if DEBUG: print 'Loading guessit module ...'
        import guessit  # @UnusedImport -- we are using this on another thread
        if DEBUG: print 'Module loaded: guessit'
        avl.guessit_available = True
    except ImportError:
        if DEBUG: print 'guessit module not available'

# pip install subliminal
def load_subliminal(avl):
    try:
        if DEBUG: print 'Loading subliminal module ...'
        import subliminal
        if DEBUG: print 'Module loaded: subliminal'
        if DEBUG: print 'Loading babelfish (for subliminal) module ...'
        import babelfish
        if DEBUG: print 'Module loaded: babelfish'
        # TODO: search subtitles with subliminal
        avl.subliminal_available = True
    except ImportError:
        if DEBUG: print 'subliminal module not available'

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
        if DEBUG: print 'Sending invalid session to', sender
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
    if DEBUG: print 'Player exited'

def camelcase(val):
    lst = val.split(' ')
    for idx in xrange(len(lst)):
        lst[idx] = lst[idx].capitalize()
    return ' '.join(lst)

def process_player_info():
    if session.info_parsed or not availability.guessit_available:
        session.socket.send(MSG_A_PLAYER_INFO, session.info, destination=session.address)
        
        if session.extra_parsed:
            session.socket.send(MSG_A_PLAYER_EXTRA, session.extra, destination=session.address)
        # if session.extra is not parsed then there is no extra or it is still in construction
        
        return
    
    import guessit # this should be fast since it is pre-loaded here
    
    if DEBUG: print 'Processing player info for', session.video
    
    guess = guessit.guess_video_info(session.video)
    if DEBUG: print 'Guessit response:', guess.nice_string()
    
    if 'type' in guess.keys():
        ftype = guess['type']

        if ftype == 'episode':
            if 'series' not in guess.keys():
                session.info_parsed = True
                return
                
            show = camelcase(guess['series'])
            
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
            
            title = camelcase(guess['title'])
                
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
    if DEBUG: print 'Received:', hex(header), data, '| From:', sender
    
    if header == MSG_A_LOGIN:
        if data == secret_keypass:
            sid = str( uuid.uuid4() )
            
            session.id      = sid
            session.socket  = sock
            session.address = sender
            
            if DEBUG: print 'Current session:', sid
            
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
            if DEBUG: print 'Current session exited'
    
    elif header == MSG_A_KEEPALIVE:
        valid, sid, data = check_session(sock, sender, data)
        if valid:
            sock.send(MSG_A_KEEPALIVE, None, destination=sender)
                
    elif header == MSG_A_LIST_FILES:
        valid, sid, directory = check_session(sock, sender, data)
        if valid:
            if not directory:
                directory = default_path
            
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
                if DEBUG: print 'Player started'
                
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

def wait_for_exit_signal():
    def handle_usr1(num, frame):
        pass
    
    signal.signal(signal.SIGUSR1, handle_usr1)
    signal.pause()
                
if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == '--debug':
            DEBUG = True
    
    mh = util.MulticastHandler(MCAST_GRP, MCAST_PORT, handler=my_handler, buffer_size=max_message_length)
    
    # pre-load some modules
    threading.Thread(target=load_guessit, name='guessit|Loader', args=(availability,)).start()
    # do not bother loading subliminal until it is integrated
    # threading.Thread(target=load_subliminal, name='subliminal|Loader', args=(availability,)).start()
    
    # raw_input('Press ENTER to exit\n')
    wait_for_exit_signal()
    
    if session.player is not None:
        session.player.exit()
    session.clear()
    
    mh.shutdown()
