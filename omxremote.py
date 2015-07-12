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
