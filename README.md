omxremote
=========

This is a Python module creating a bridge between an Android client and 
an omxplayer on a Raspberry Pi. This module is able to start a player
and send commands to it (like pause, seek, set volume, etc.)

This module needs a modified version of the omxplayer which can be found here:

    https://github.com/rycus86/omxplayer

There is an Android client project to control the player through this library:

    https://github.com/rycus86/omxremote-android

Installation and startup
------------------------

I will create a description with instructions for configuration but right now:

    python omxremote.py (add --debug to see some debug messages)

How does it work?
-----------------

The module creates a multicast socket on the Pi at 224.1.1.7:42001 and 
waits for an Android client to join. After an initial message reception 
the Android and Python modules communicate with unicast messages on the 
given UDP port of the multicast socket.
On a playback start request the Python module starts an instance of the
(modified) omxplayer and waits for it to connect back to the TCP socket
also created by the Python module. After this the module periodically polls
the player for its state and sends it to the Android client. The Android 
side can also send commands to the module which in turn dispatches them
to the player.

Current status
--------------

This is an initial version of the remote and I have some ideas for future
improvements. Currently it is capable of the following things:

    Handle a connection to an Android client
    Start an instance of omxplayer and query state informations from it
    Player functions: Play, Pause, Seek, Set Volume, Set Speed, Set Subtitle Delay, Toggle Subtitle
    Guessing information of the started video file
    Fetching information from TVDB when playing an episode of a show

Future improvements
-------------------

I'd like to implement these features when I have time for it:

    Fetching (movie/show) information from IMDB
    Searching and downloading subtitles with subliminal
    Provide a TCP server socket for the Android client

Dependencies
------------

There are some very awesome projects you should check out in relation to this project.

    omxplayer : https://github.com/popcornmix/omxplayer/
    guessit   : https://pypi.python.org/pypi/guessit
    subliminal: https://pypi.python.org/pypi/subliminal

Feedback
--------

You are welcome to give feedback, ideas and report issues. I'd like to
improve this project when I find the time for it. Until then feel free to
fork and improve it.
