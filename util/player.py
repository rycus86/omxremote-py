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


class _DbusPlayer(object):

    def __init__(self, video, subtitle, args):
        self.__args = args

        self.video = video
        self.subtitle = subtitle

        self.info = None
        self.info_parsed = False

        self.extra = None
        self.extra_parsed = False

        self.get_info()  # pre-load info
        self.get_extras()  # pre-load extras

        self.__exit_requested = False
        self.__process = None

        self.__start_process()

        self.__dbus_properties = None
        self.__dbus_keys = None

        self.__initialize_dbus()

    def __start_process(self):
        self.__process = subprocess.Popen(self.__args)

    def __initialize_dbus(self):
        for _ in xrange(20):
            try:
                self.__dbus_properties = None
                self.__dbus_keys = None

                omxplayerdbus = None

                for suffix in (os.getenv('USERNAME', 'root'), os.getenv('USER', 'root'), ''):
                    dbus_file_path = '/tmp/omxplayerdbus.%s' % suffix
                    if os.path.exists(dbus_file_path):
                        with open(dbus_file_path, 'r+') as dbus_file:
                            omxplayerdbus = dbus_file.read().strip()
                            break

                if omxplayerdbus:
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
            return os.path.basename(self.video)

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
        try:
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

                elif ftype == 'movie':
                    if 'title' not in guess.keys():
                        return

                    title = util.camelcase(guess['title'])
                    year = guess.get('year')

                    self.info = {
                        'type': 'movie',
                        'title': title,
                        'year': year
                    }

            return self.info
        finally:
            self.info_parsed = True

    def get_extras(self):
        if self.extra_parsed:
            return self.extra

        try:
            info = self.get_info()
            if not info or info.get('type', '') != 'episode':
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

            return self.extra
        finally:
            self.extra_parsed = True
