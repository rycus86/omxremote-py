'''
Created on Oct 10, 2013

@author: rycus
'''

import sqlite3

class _Settings(object):
    
    # TODO: use default values
    # fields:  key             description                               values   default  type   scale
    all  = [ ( 'vol',          'Initial volume in decibels',                None, '0',  'NUMBER', 100  ), \
             ( 'font-size',    'Font size as thousandths of screen height', None, '55', 'NUMBER', 1    ), \
             ( 'align',        'Subtitle alignment',                    'left,center', 'left', 'ENUM', None ), \
             ( 'no-osd',       'Do not display content on display',         None, True,  'SWITCH', None ), \
             ( 'no-ghost-box', 'No semitransparent boxes behind subtitles', None, False, 'SWITCH', None ), \
             ( 'additional',   'Additional command line arguments',         None, '',    'TEXT',   None ) ]
    
    keys = [ k for (k, d, v, df, t, s) in all ]
    
    __connection = None
    
    @classmethod
    def __connect(cls):
        if _Settings.__connection is None:
            db = sqlite3.connect('omxremote.db')
            try:
                db.execute('SELECT 1 FROM settings')
            except:
                # create database tables
                with db: db.execute('CREATE TABLE settings (key PRIMARY KEY, value)')
            _Settings.__connection = db
        return _Settings.__connection
    
    @classmethod
    def default(cls, key):
        for (_key, d, v, _default, t, s) in _Settings.all:  # @UnusedVariable
            if _key == key:
                return _default
        return None
    
    @classmethod
    def type_of(cls, key):
        for (_key, d, v, df, _type, s) in _Settings.all:  # @UnusedVariable
            if _key == key:
                return _type
        return None
    
    @classmethod
    def scale_of(cls, key):
        for (_key, d, v, df, t, _scale) in _Settings.all:  # @UnusedVariable
            if _key == key:
                return _scale
        return None
    
    @classmethod
    def get(cls, key):
        with _Settings.__connect() as db:
            value = db.execute('SELECT value FROM settings WHERE key = ?', (key, )).fetchone()
            if value:
                (ret, ) = value
                return ret
            else:
                return _Settings.default(key)
    
    @classmethod
    def set(cls, key, value):
        with _Settings.__connect() as db:
            if value is None:
                db.execute('DELETE FROM settings WHERE key = ?', (key, ))
            else:
                oldvalue = db.execute('SELECT value FROM settings WHERE key = ?', (key, )).fetchone()
                if oldvalue:
                    db.execute('UPDATE settings SET value = ? WHERE key = ?', (value, key, ))
                else:
                    db.execute('INSERT INTO settings VALUES (?, ?)', (key, value, ))
    