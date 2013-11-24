'''
RaspberryPi::omxplayer Remote for Android

Common classes used in this project.

Created on Oct 1, 2013

@author: rycus
'''

from util import player, mcast, settings, tvdb

import os

# declare utility classes
class Flags(mcast._Flags): pass
class MulticastHandler(mcast._MulticastHandler): pass
class Settings(settings._Settings): pass
class PlayerProcess(player._PlayerProcess): pass

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
    
    has_parent = directory != '/'
    
    if has_parent:
        return directory + '||../|' + ( '|'.join(results) )
    else:
        return directory + '||' + ( '|'.join(results) )
