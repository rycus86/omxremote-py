'''
RaspberryPi::omxplayer Remote for Android

Common classes used in this project.

Created on Oct 1, 2013

@author: rycus
'''

# utility modules
from util import player, settings, tvdb

from client import start as start_client

# subtitle modules
import subtitles
# enumerate modules to load subtitle providers from
from subtitles import addic7ed, supersubtitles
from subtitles.subliminal import opensubtitles

import os
import re
import subprocess
import time
import threading

# declare utility classes
# class Flags(mcast._Flags): pass
# class MulticastHandler(mcast._MulticastHandler): pass
class Settings(settings._Settings): pass
class PlayerProcess(player._DbusPlayer): pass

class Subtitles(subtitles.SubtitleProvider): pass
class SubtitleQuery(subtitles.SubtitleQuery): pass

# -- Other utility methods --

video_extensions    = [ '.avi', '.mp4', '.mkv' ]
subtitle_extensions = [ '.srt' ]

def create_file_list(directory):
    results = []
    
    directory = os.path.abspath(directory)
    
    if os.path.exists(directory):
        for sub in os.listdir(directory):
            if sub[0] == '.': continue # hidden files
            
            if os.path.isdir(os.path.join(directory, sub)):
                results.append(sub + '/')
            else:
                fname, ext = os.path.splitext(sub)  # @UnusedVariable
                if ext.lower() in video_extensions or ext.lower() in subtitle_extensions:
                    results.append(sub)
    
    results.sort()

    if directory != '/':  # has parent
        results = ['../'] + results

    return results

def create_file_list_str(directory):
    results = create_file_list(directory)

    has_parent = directory != '/'

    if has_parent:
        return directory + '||../|' + ( '|'.join(results) )
    else:
        return directory + '||' + ( '|'.join(results) )

def recode_file(source):
    mime = subprocess.Popen([ 'file', '-bi', source ], stdout=subprocess.PIPE).stdout.read().strip()
    if re.match('^text\\/.*; charset=.*$', mime):
        charset = re.sub('^text\\/.*; charset=(.*)$', '\\1', mime)
        if charset.lower() == 'utf-8':
            pass # File is already encoded in UTF-8
        else:
            try:
                exp  = charset + '..utf-8'
                proc = subprocess.Popen([ 'recode', exp, source ])
                ret  = proc.wait()
                if ret == 0:
                    pass # File recoded
                else:
                    print 'File [' + source + '] recode failed with code:', ret
            except OSError:
                print 'File [' + source + '] recode failed, recode executable not found'
    else:
        pass # This file does not appear to be a plain text file

def camelcase(val):
    lst = val.split(' ')
    for idx in xrange(len(lst)):
        lst[idx] = lst[idx].capitalize()
    return ' '.join(lst)

class CountdownLatch(object):

    def __init__(self, count):
        self.__count = count
        self.__condition = threading.Condition()

    def countdown(self):
        with self.__condition:
            self.__count -= 1

            if self.__count == 0:
                self.__condition.notify()

    def await(self, timeout = None):
        start = time.time()
        with self.__condition:
            while self.__count > 0:
                if timeout is not None:
                    t_elapsed   = time.time() - start
                    t_remaining = timeout - t_elapsed
                    if t_remaining > 0:
                        self.__condition.wait(t_remaining)
                    else:
                        return self.__count
                else:
                    self.__condition.wait()

            return 0
