#!/usr/bin/python3
import threading
import queue
import sys
import fcntl
import os
import select
import argparse
dependencies="""
Debian 11:
 apt install python3-websocket
Others:
 pip3 install websocket-client
"""

try:
    import websocket
except ModuleNotFoundError as e:
    print("Missing dependencies: {}".format(repr(e)))
    print("Please install dependencies: {dependencies}".format(dependencies=dependencies))
    sys.exit(1)

class WebSocketReader(threading.Thread):
    def __init__(self, event_queue, socket):
        threading.Thread.__init__(self)
        self.event_queue = event_queue
        self.socket = socket

    def run(self):
        while True:
            try:
                data = self.socket.recv()
            except Exception as e:
                print(f"WebSocketReader got exception {e}", file=sys.stderr)
                data = b""
            if data == "":
                data = b""
            self.event_queue.put((self.socket, data))
            if data == b"":
                break

class StreamReader(threading.Thread):
    def __init__(self, event_queue, stream):
        threading.Thread.__init__(self)
        self.event_queue = event_queue
        self.stream = stream

    def run(self):
        epoll = select.epoll()
        epoll.register(self.stream.fileno(), select.EPOLLIN)

        end_of_stream = False
        try:
            while not end_of_stream:
                events = epoll.poll(1)
                for fileno, event in events:
                    data = self.stream.read(4096)
                    if data is None:
                        data = b""
                    self.event_queue.put((self.stream, data))
                    if data == b"":
                        end_of_stream = True
        finally:
            epoll.unregister(self.stream.fileno())
            epoll.close()
                    

def set_nonblocking(fd):
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Connect to SSH port of a running baremetal instance")
    parser.add_argument("-a", "--api-key", metavar="FILE", required=True, help="File with API key")
    parser.add_argument("WEBSOCKET_BASE_URL", help="URL of the websocket")
    args = parser.parse_args()

    with open(args.api_key) as f:
        apikey = f.read().strip()

    header = {
        "X-API-KEY": apikey
    }
    web_socket = websocket.create_connection(f"{args.WEBSOCKET_BASE_URL}/connect-to-ssh", header=header)

    set_nonblocking(sys.stdin.buffer.fileno())

    event_queue = queue.Queue()

    WebSocketReader(event_queue, web_socket).start()
    StreamReader(event_queue, sys.stdin.buffer).start()
    
    while True:
        #print(f"Waiting for events")
        source_socket, data = event_queue.get()
        #print(f"Got {repr(data)} from {source_socket}", file=sys.stderr)
    
        if source_socket == web_socket:
            if data == b"C":
                break
            else:
                sys.stdout.buffer.write(data[1:])
                sys.stdout.buffer.flush()
        elif source_socket == sys.stdin.buffer:
            if data == b"":
                web_socket.send_binary(b"C")
                break
            else:
                web_socket.send_binary(b"D" + data)
        else:
            print(f"Internal error, unknown source_socket {source_socket}", file=sys.stderr)
            sys.exit(1)

    sys.stdout.buffer.close()
    web_socket.close()


