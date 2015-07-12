import omxremote

__author__ = 'rycus'


import util

import os
import json
import socket
import threading
import BaseHTTPServer
import SocketServer
import httplib


class RestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def parse_request(self):
        parsed = BaseHTTPServer.BaseHTTPRequestHandler.parse_request(self)
        if parsed:
            if 'RPi::omxremote|v2' == self.headers.get('X-RPi-OmxPlayer', ''):
                print 'Handling %s request for %s' % (self.command, self.path)
                return True
            else:
                self.send_error(httplib.FORBIDDEN)

        return False

    def do_GET(self):
        if self.path == '/list/settings':
            items = []

            for (key, desc, values, default, stype, scale) in util.Settings.all:
                value = util.Settings.get(key)
                if stype == 'SWITCH':
                    value = ('1' if value is not None and value else '0')
                if stype == 'NUMBER':
                    value = str(int(value) / scale)

                items.append({
                    'key': key,
                    'description': desc,
                    'possibleValues': values,
                    'type': stype,
                    'value': value
                })

            self.send_response_json(items)

        elif self.path == '/player/state':
            player = self.server.get_player()
            if player:
                position, volume, paused = player.get_state()

                self.send_response_json({
                    'videofile': player.video,
                    'title': player.get_title(),
                    'info': player.get_alt_title(),
                    'duration': player.get_duration(),
                    'position': position,
                    'volume': int(volume / 100),
                    'paused': paused,
                    'extras': player.get_extras()
                })

            else:
                if self.server.is_player_running():
                    self.send_error(httplib.INTERNAL_SERVER_ERROR)
                else:
                    self.server.stop_player()
                    self.send_error(httplib.NO_CONTENT)

    def do_POST(self):
        if self.path == '/list/files':
            data = self.read_json_body()
            path = data.get('path')

            if not path:
                path = self.server.root_path

            flist = util.create_file_list(path)

            self.send_response_json({'path': os.path.abspath(path), 'files': flist})

        elif self.path == '/set/setting':
            data = self.read_json_body()
            key, value = data.get('key'), data.get('value')
            print 'New setting value: %s = %s' % (key, value)

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

            self.send_ok()

        elif self.path == '/player/start':
            data = self.read_json_body()
            video, subtitle = data.get('video'), data.get('subtitle')
            print 'Starting video "%s" with subtitle "%s"' % (video, subtitle)

            player = self.__start_video(video, subtitle)
            duration, volume = player.init()

            self.send_response_json({
                'videofile': video,
                'title': player.get_title(),
                'info': player.get_alt_title(),
                'duration': duration,
                'position': 0,
                'volume': int(volume / 100),
                'paused': False,
                'extras': player.get_extras()
            })

        elif self.path == '/player/stop':
            self.server.stop_player()
            self.send_ok()

        elif self.path.startswith('/player/ctrl/'):
            command = self.path[len('/player/ctrl/'):]
            data = self.read_json_body()

            player = self.server.get_player()
            if not player:
                self.send_error(httplib.NOT_FOUND)
                return

            if command == 'play/pause':
                player.pause()
                self.send_ok()

            elif command == 'volume':
                if data and 'param' in data:
                    value = int(data.get('param')) * 100
                    player.set_volume(value)
                    self.send_ok()
                else:
                    self.send_error(httplib.BAD_REQUEST)

            elif command == 'seek':
                if data and 'param' in data:
                    value = int(data.get('param')) / 1000
                    player.seek_to(value)
                    self.send_ok()
                else:
                    self.send_error(httplib.BAD_REQUEST)

            elif command == 'speed/inc':
                player.increase_speed()
                self.send_ok()

            elif command == 'speed/dec':
                player.decrease_speed()
                self.send_ok()

            elif command == 'subtitle/delay/inc':
                player.increase_subtitle_delay()
                self.send_ok()

            elif command == 'subtitle/delay/dec':
                player.decrease_subtitle_delay()
                self.send_ok()

            elif command == 'subtitle/toggle':
                player.toggle_subtitle_visibility()
                self.send_ok()

        elif self.path == '/subtitles/metadata':
            data = self.read_json_body()
            filename = data.get('filename')

            query = util.SubtitleQuery(filename)
            query.set_is_a_filename()
            query.guess_season_and_episode()

            response = {
                'show': query.show,
                'season': query.season,
                'episode': query.episode,
                'providers': [p.name() for p in util.Subtitles.providers()]
            }

            self.send_response_json(response)

        elif self.path == '/subtitles/query':
            data = self.read_json_body()

            provider_name = data.get('provider')
            filename = data.get('query')

            print 'Executing query for %s on %s provider' % (filename, provider_name)

            query = util.SubtitleQuery(filename)
            query.set_is_a_filename()
            query.guess_season_and_episode()

            provider = util.Subtitles.provider_by_name(provider_name)
            if provider:
                self.send_response(httplib.OK)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()

                for item in provider.query(query):
                    util.Subtitles.Cache.add(provider, item)

                    part = item.to_dict()
                    print 'Found subtitle: %s' % part

                    json.dump(part, self.wfile)

                    self.wfile.write('\n')
                    self.wfile.flush()

            else:
                self.send_error(httplib.BAD_REQUEST)

            self.finish()

        elif self.path == '/subtitles/download':
            data = self.read_json_body()

            provider_name = data.get('provider')
            sub_id = data.get('id')
            directory = data.get('directory')

            provider = util.Subtitles.provider_by_name(provider_name)
            item = util.Subtitles.Cache.get(provider, sub_id)

            if item:
                downloaded = provider.download(item.id, directory)
                if downloaded:
                    util.Subtitles.Cache.clear()

                    self.send_response_json({'success': True, 'path': downloaded})

                else:
                    self.send_error(httplib.INTERNAL_SERVER_ERROR)

            else:
                self.send_error(httplib.NOT_FOUND)

    def read_json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length:
            raw = self.rfile.read(length)
            return json.loads(raw)

    def send_response_json(self, data):
        self.send_response(httplib.OK)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        print 'Sending response: %s' % data

        json.dump(data, self.wfile)

    def send_ok(self):
        self.send_response(httplib.OK)
        self.end_headers()

    def __start_video(self, video, subtitle):
        if not os.path.exists(video):
            self.send_error(httplib.NOT_FOUND, 'Video file not found')
            return

        if subtitle and not os.path.exists(subtitle):
            self.send_error(httplib.NOT_FOUND, 'Subtitle file not found')
            return

        return self.server.start_player(video, subtitle)


class Server(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):

    advertiser = None
    player = None
    root_path = os.path.expanduser('~')

    def set_root_path(self, path):
        self.root_path = path

    def advertise(self, group, port):
        self.advertiser = ServerAdvertiser(group, port, self.server_port)
        self.advertiser.start()

    def start(self):
        print 'Starting server on port %d' % self.server_port
        threading.Thread(target=self.serve_forever).start()

    def shutdown(self):
        self.stop_player()
        self.advertiser.shutdown()
        BaseHTTPServer.HTTPServer.shutdown(self)

    def start_player(self, video, subtitle):
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

        old_player = self.player
        if old_player:
            old_player.exit()

        new_player = util.PlayerProcess(video, subtitle, commands)
        self.player = new_player
        return new_player

    def stop_player(self):
        if self.player:
            self.player.exit()

        self.player = None

    def get_player_state(self):
        if self.is_player_running():
            return self.player.get_state()

    def is_player_running(self):
        return self.player and self.player.is_valid()

    def get_player(self):
        if self.is_player_running():
            return self.player


class ServerAdvertiser(object):

    def __init__(self, group, port, advertised_port,
                 ttl=8, loopback=False, reuse_address=True,
                 read_timeout=0.5, buffer_size=4096):

        self.__mcast_sock = None

        self.__group = group
        self.__port = port
        self.__advertised_port = advertised_port

        self.__ttl = ttl
        self.__loopback = loopback
        self.__reuse_address = reuse_address
        self.__timeout = read_timeout
        self.__buffer_size = buffer_size

        self.__shutdown = False

    def start(self):
        self.__mcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.__mcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,      self.__reuse_address)
        self.__mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL,  self.__ttl)
        self.__mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, self.__loopback)
        self.__mcast_sock.settimeout(self.__timeout)
        self.__mcast_sock.bind(('0.0.0.0', self.__port))

        import struct
        mreq = struct.pack("4sl", socket.inet_aton(self.__group), socket.INADDR_ANY)
        self.__mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        bound_port = self.__mcast_sock.getsockname()[1]

        print 'Multicast socket bound on', str(self.__group) + ':' + str(bound_port)

        threading.Thread(target=self.accept).start()

    def accept(self):
        while not self.__shutdown:
            try:
                data, sender = self.__mcast_sock.recvfrom(self.__buffer_size)
                if data == 'RPi::omxremote|v2':
                    print 'Responding to ping for %s' % str(sender)
                    message = '%05d' % self.__advertised_port
                    self.__mcast_sock.sendto(message, sender)
            except socket.timeout:
                pass  # OK, timeout

    def shutdown(self):
        self.__shutdown = True


def start(root_path, advertise_group, advertise_port, http_port=0):
    server = Server(('', http_port), RestHandler)
    server.set_root_path(root_path)
    server.advertise(advertise_group, advertise_port)
    server.start()
    return server
