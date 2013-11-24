'''
Created on Oct 10, 2013

@author: rycus
'''

import omxremote

import socket
import traceback
import threading

# message flags
class _Flags(object): 
    MORE_FOLLOWS = 0x01 << 0

class _MulticastHandler(object):
    
    def __init__(self, group, port, handler=None, \
                 ttl=8, loopback=False, reuse_address=True, \
                 read_timeout=0.5, buffer_size=1500):
        
        self.__enabled = True
        
        self.__group   = group
        self.__port    = port
        self.__handler = handler
        
        self.__ttl           = ttl
        self.__loopback      = 1 if loopback      else 0
        self.__reuse_address = 1 if reuse_address else 0
        self.__timeout       = read_timeout
        self.__buffer_size   = buffer_size
        self.__send_lock     = threading.RLock()
        
        self.__create_socket()
        
        self.__receiver = self.__create_receiver()
        self.__receiver.start()
        
        self.__incomplete_messages = { }
        
    def __create_socket(self):
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
        
        if omxremote.DEBUG: print 'Multicast socket bound on', str(self.__group) + ':' + str(bound_port)
    
    def __merge_incomplete(self, header, data, sender, finish):
        if sender not in self.__incomplete_messages:
            self.__incomplete_messages[sender] = { }
            
        by_header = self.__incomplete_messages[sender]
        
        if header in by_header:
            merged = by_header[header] + data
            if finish:
                del by_header[header]
            else:
                by_header[header] = merged
            return merged
        else:
            if not finish:
                by_header[header] = data
            return data
    
    def __do_receive(self):
        ''' Waiting for data on multicast socket '''
        while self.__enabled:
            try:
                data, sender = self.__mcast_sock.recvfrom(self.__buffer_size)
                if self.__enabled and len(data) >= 2:
                    header, flags, message = ord(data[0]), ord(data[1]), data[2:]
                    finish = (flags & _Flags.MORE_FOLLOWS) != _Flags.MORE_FOLLOWS
                    merged = self.__merge_incomplete(header, message, sender, finish)
                    
                    if finish:
                        self.__handler(self, sender, header, merged)
            except socket.timeout:
                pass # no data received in timeout interval, but it is normal
            except Exception as ex:
                if omxremote.DEBUG: 
                    print 'Exception received on multicast receiver thread:', ex
                    traceback.print_exc()
    
    def __create_receiver(self):
        if self.__handler is None:
            def __handle(handler, sender, header, data):
                # default handler implementation
                print 'Received:', hex(header), data, 'from', sender
            self.__handler = __handle
            
        return threading.Thread(target=self.__do_receive, name='Multicast|Receiver')
    
    def get_buffer_size(self):
        return self.__buffer_size
    
    def send(self, header, data, destination=None, buffer_size=None, flags=0):
        self.__send_lock.acquire()
        try:
            if destination is None:  destination = (self.__group, self.__port)
            
            buf_size = buffer_size if buffer_size is not None else self.__buffer_size
            max_size = buf_size - 2 # BufferSize - (HeaderLength + FlagsLength)
            
            # if isinstance(header, (int, long)):
            header = chr(header)
            
            if data is None:
                data = ''
                
            data = data.encode('ascii', 'ignore')
            data_len = len(data)
            
            while len(data) > max_size: # send the splitted parts first
                flags |= _Flags.MORE_FOLLOWS
                part = header + chr(flags) + data[0:max_size]
                self.__mcast_sock.sendto(part, destination)
                data = data[max_size:]
            
            flags &= ~ _Flags.MORE_FOLLOWS
            
            if data or data_len == 0: # send the rest of the message
                part = header + chr(flags) + data
                self.__mcast_sock.sendto(part, destination)
        finally:
            self.__send_lock.release()
        
    def shutdown(self):
        self.__enabled = False
        self.__mcast_sock.close()
