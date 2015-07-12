'''
Created on Oct 10, 2013

@author: rycus
'''

import omxremote
import util

import socket
import subprocess
import threading
import time
import dbus
import os

# omxremote message identifiers
MSG_EXIT            = chr(0xFE)
MSG_INIT            = chr(0x01)
MSG_PAUSE           = chr(0x11)
MSG_SPEED_DEC       = chr(0x12)
MSG_SPEED_INC       = chr(0x13)
MSG_SUB_DELAY_DEC   = chr(0x14)
MSG_SUB_DELAY_INC   = chr(0x15)
MSG_SUB_SHOW        = chr(0x16)
MSG_VOLUME          = chr(0x21)
MSG_SEEK_TO         = chr(0x22)
MSG_PLAYER_STATE    = chr(0x31)

def _to_long(data, offset):
    negative = (ord(data[offset]) & 0x80) == 0x80
    data     = data[:offset] + chr(ord(data[offset]) & 0x7F) + data[offset+1:]
    
    val = 0
    
    for idx in xrange(4):
        shift = (4 - 1 - idx) * 8
        val = val + (ord(data[offset + idx]) << shift)
    
    return -val if negative else val

def _to_string(value):
    negative = value < 0
    if negative:
        value = -value
    
    buf = ''

    for idx in xrange(4):
        shift = (4 - 1 - idx) * 8;
        mask  = 0xFF << shift;
        b     = (value & mask) >> shift;

        buf += chr(b & 0xFF)
    
    if negative:
        buf = chr(ord(buf[0]) | 0x80) + buf[1:]
    
    return buf

class _Receiver(threading.Thread):
    
    def __init__(self, socket, callback):
        threading.Thread.__init__(self, target=self.__handle, name='PlayerProcess|Receiver')
        
        self.__socket   = socket
        self.__callback = callback
        self.start()
    
    def __handle(self):
        sock = self.__socket
        
        while True:
            # TODO: how to handle exceptions?
            
            rd = sock.recv(1)
            if rd == MSG_EXIT:
                if omxremote.is_debug(): print self.name, 'exiting'
                break
            
            length = ord(rd[0])
            
            data   = sock.recv(length)
            head, data = data[0], data[1:]
            
            self.__callback(head, data)
    
class _PlayerProcess(threading.Thread):
    
    def __init__(self, args):
        threading.Thread.__init__(self, target=self.__handle_connection, name='PlayerProcess')
        
        self.__args = args
        
        self.__process        = None
        
        self.__client_socket  = None
        self.__server_socket  = None
        self.__server_port    = -1
        self.__receiver       = None
        
        self.__start_condition  = threading.Condition()
        self.__lock_condition   = threading.Condition()
        
        self.__callback_data  = None
        
        self.__exit_requested = False
        
        self.__prepare()
        
        if omxremote.is_debug():print 'Starting player on port', self.__server_port
        if omxremote.is_debug():print '\t', ' '.join(self.__args)
        
        self.__args.append('--bridge=' + str(self.__server_port))
        
        self.start()
    
    def __prepare(self):
        ss = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ss.bind( ('127.0.0.1', 0) )
        ss.listen(1)
        self.__server_socket = ss
        self.__server_port   = ss.getsockname()[1]
    
    def start(self):
        threading.Thread.start(self)
        
        try:
            self.__run_omxplayer()
        except Exception as ex: # there was an error starting the process
            self.exit()
            raise ex
    
    def __handle_connection(self):
        (self.__client_socket, address) = self.__server_socket.accept()
        if omxremote.is_debug():print 'Player socket accepted from', address
        
        self.__start_condition.acquire()
        try:
            self.__receiver = _Receiver(self.__client_socket, self.__on_callback)
            # notify on start        
            self.__start_condition.notify()
        finally:
            self.__start_condition.release()
    
    def __on_callback(self, header, data):
        if header == MSG_INIT:
            duration = _to_long(data, 0)
            volume   = _to_long(data, 4)
            self.__set_callback_data( (duration, volume) )
        
        elif header == MSG_PLAYER_STATE:
            position = _to_long(data, 0)
            volume   = _to_long(data, 4)
            paused   = data[8] == 'P'
            self.__set_callback_data( (position, volume, paused) )
            
        else:
            if omxremote.is_debug(): print 'Unknown player callback received:', header, hex(header)
    
    def __set_callback_data(self, data):
        self.__lock_condition.acquire()
        try:
            self.__callback_data = data
            self.__lock_condition.notify()
        finally:
            self.__lock_condition.release()
    
    def __run_omxplayer(self):
        self.__process = subprocess.Popen(self.__args)
    
    def __send_for_result(self, message):
        result = None
        
        if self.__receiver is not None:
            self.__lock_condition.acquire()
            try:
                self.__client_socket.send(message)
                self.__lock_condition.wait(1)
                result = self.__callback_data
            finally:
                self.__lock_condition.release()
        
        return result
    
    def init(self):
        self.__start_condition.acquire()
        try:
            if self.__receiver is None:
                self.__start_condition.wait(30)
        finally:
            self.__start_condition.release()
        
        return self.__send_for_result(MSG_INIT)
    
    def get_state(self):
        return self.__send_for_result(MSG_PLAYER_STATE)
    
    def set_volume(self, volume):
        self.__client_socket.send( MSG_VOLUME + _to_string(volume) )
    
    def seek_to(self, timestamp):
        self.__client_socket.send( MSG_SEEK_TO + _to_string(timestamp) )
        
    def pause(self):
        self.__client_socket.send( MSG_PAUSE )
        
    def increase_speed(self):
        self.__client_socket.send( MSG_SPEED_INC )
        
    def decrease_speed(self):
        self.__client_socket.send( MSG_SPEED_DEC )
        
    def increase_subtitle_delay(self):
        self.__client_socket.send( MSG_SUB_DELAY_INC )
        
    def decrease_subtitle_delay(self):
        self.__client_socket.send( MSG_SUB_DELAY_DEC )
        
    def toggle_subtitle_visibility(self):
        self.__client_socket.send( MSG_SUB_SHOW )
    
    def is_valid(self):
        process_is_valid    = self.__process.poll() is None
        exit_not_requested  = not self.__exit_requested
        return process_is_valid and exit_not_requested
    
    def exit(self):
        self.__exit_requested = True
        
        if self.__client_socket:
            self.__client_socket.send(MSG_EXIT)
        self.__server_socket.close()
        
        def __kill_process():
            time.sleep(3) # give it 3 seconds to exit
            if self.__process.poll() is None:
                self.__process.kill()
                if omxremote.is_debug(): print 'External player process killed, PID:', self.__process.pid
                
        threading.Thread(target=__kill_process, name='PlayerProcess|Killer').start()
        
        return self.__process.wait()


class _DbusPlayer(object):

    def __init__(self, video, subtitle, args):
        self.__args = args

        self.__exit_requested = False

        self.__process = None

        self.__start_process()

        self.__dbus_properties = None
        self.__dbus_keys = None

        self.__initialize_dbus()

        self.video = video
        self.subtitle = subtitle

        self.info = None
        self.info_parsed = False

        self.extra = None
        self.extra_parsed = False

    def __start_process(self):
        self.__process = subprocess.Popen(self.__args)

    def __initialize_dbus(self):
        for _ in xrange(20):
            try:
                self.__dbus_properties = None
                self.__dbus_keys = None

                with open('/tmp/omxplayerdbus.%s' % os.getenv('USERNAME', 'root'), 'r+') as dbus_file:
                    omxplayerdbus = dbus_file.read().strip()

                bus = dbus.bus.BusConnection(omxplayerdbus)
                object = bus.get_object('org.mpris.MediaPlayer2.omxplayer', '/org/mpris/MediaPlayer2', introspect=False)
                self.__dbus_properties = dbus.Interface(object, 'org.freedesktop.DBus.Properties')
                self.__dbus_keys = dbus.Interface(object, 'org.mpris.MediaPlayer2.Player')

                if self.__dbus_properties and self.__dbus_keys:
                    break
            except:
                if omxremote.is_debug(): 'DBus is not ready'

            time.sleep(0.5)

    def init(self):
        duration = self.get_duration()
        volume = self.__dbus_properties.Volume()

        # (duration, volume)
        return duration, int(volume)

    def get_duration(self):
        duration = self.__dbus_properties.Duration()
        return int(duration) / 1000

    def get_state(self):
        position = self.__dbus_properties.Position()
        volume = self.__dbus_properties.Volume()
        paused = self.__dbus_properties.PlaybackStatus()

        # (position, volume, paused)
        return int(position) / 1000, int(volume), str(paused) == 'Paused'

    def set_volume(self, volume):
        self.__dbus_properties.Volume(dbus.Double((100 + volume) / 100.0))

    def seek_to(self, timestamp):
        self.__dbus_keys.SetPosition(dbus.ObjectPath('/not/used'), long(timestamp * 1000000))

    def pause(self):
        self.__dbus_keys.PlayPause()

    def increase_speed(self):
        self.__dbus_keys.Action(dbus.Int32("2"))

    def decrease_speed(self):
        self.__dbus_keys.Action(dbus.Int32("1"))

    def increase_subtitle_delay(self):
        self.__dbus_keys.Action(dbus.Int32("14"))

    def decrease_subtitle_delay(self):
        self.__dbus_keys.Action(dbus.Int32("13"))

    def toggle_subtitle_visibility(self):
        self.__dbus_keys.Action(dbus.Int32("12"))

    def is_valid(self):
        return not self.__exit_requested and self.__process.poll() is None

    def exit(self):
        self.__exit_requested = True

        def __send_exit():
            # TODO there is a Quit
            if self.__process.poll() is None:
                self.__dbus_keys.Action(dbus.Int32("15"))

        def __kill_process():
            __send_exit()

            time.sleep(3) # give it 3 seconds to exit
            if self.__process.poll() is None:
                print 'Killing process as it has not exited normally'  # TODO debug
                self.__process.terminate()
                self.__process.kill()
                if omxremote.is_debug(): print 'External player process killed, PID:', self.__process.pid
            else:
                if omxremote.is_debug(): print 'The process has stopped normally'

        threading.Thread(target=__kill_process, name='PlayerProcess|Killer').start()

        return self.__process.wait()

    def get_title(self):
        info = self.get_info()
        extra = self.get_extras()

        if extra and 'ST' in extra:
            return extra['ST']
        elif info and 'title' in info:
            return info['title']
        else:
            return self.video

    def get_alt_title(self):
        info = self.get_info()
        if info:
            if info.get('type', '') == 'episode':
                return 'season %02d episode %02d' % (info.get('season', 0), info.get('episode', 0))
            elif info.get('type', '') == 'movie':
                return 'year %d' % info.get('year')
        else:
            return ''

    def get_info(self):
        guessit_available = False
        try:
            import guessit
            guessit_available = True
        except ImportError:
            pass  # guessit not available

        if self.info_parsed or not guessit_available:
            return self.info

        print 'Loading info for %s' % self.video

        guess = guessit.guess_video_info(os.path.basename(self.video))
        print 'Guessit response:', guess.nice_string()

        if 'type' in guess.keys():
            ftype = guess['type']

            print 'Guessit file type: %s' % ftype

            if ftype == 'episode':
                if 'series' not in guess.keys():
                    self.info_parsed = True
                    return

                show = util.camelcase(guess['series'])

                season = int(guess.get('season', '0'))
                episode = int(guess.get('episodeNumber', '0'))

                self.info = {
                    'type': 'episode',
                    'title': show,
                    'season': season,
                    'episode': episode
                }

                self.info_parsed = True

                if show and season and episode:
                    self.get_extras()  # pre-load extras

            elif ftype == 'movie':
                if 'title' not in guess.keys():
                    self.info_parsed = True
                    return

                title = util.camelcase(guess['title'])
                year = guess.get('year')

                self.info = {
                    'type': 'movie',
                    'title': title,
                    'year': year
                }

                self.info_parsed = True

        return self.info

    def get_extras(self):
        if self.extra_parsed:
            return self.extra

        info = self.get_info()
        if not info or info.get('type', '') != 'episode':
            self.extra_parsed = True
            return

        print 'Loading extras for %s | info: %s' % (self.video, info)

        series = info.get('title')
        season = info.get('season')
        episode = info.get('episode')

        sd, ed = util.tvdb.parse_tvdb_info(series, season, episode)

        extras = {}

        # series data
        if 'title'  in sd: extras['ST'] = sd['title']
        if 'imdb'   in sd: extras['SI'] = sd['imdb']
        if 'poster' in sd: extras['SP'] = sd['poster']

        # episode data
        if 'title'  in ed: extras['ET'] = ed['title']
        if 'date'   in ed: extras['ED'] = ed['date']
        if 'rating' in ed: extras['ER'] = ed['rating']
        if 'imdb'   in ed: extras['EI'] = ed['imdb']
        if 'poster' in ed: extras['EP'] = ed['poster']

        self.extra = extras
        self.extra_parsed = True

        return self.extra
