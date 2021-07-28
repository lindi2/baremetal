#!/usr/bin/python3
import socketserver
import argparse
import queue
import threading
import time
import socket
import json
import binascii
import base64

class BaremetalLogger(socketserver.BaseRequestHandler):
    def __init__(self, event_queue, *args):
        self.event_queue = event_queue
        socketserver.BaseRequestHandler.__init__(self, *args)
    def handle(self):
        message = b""
        try:
            self.request.settimeout(10)
            while True:
                data = self.request.recv(1024)
                self.request.settimeout(1)
                if data == b"":
                    break
                message += data
        except socket.timeout as e:
            pass
        if message != b"":
            self.event_queue.put(["data", message])
            
class SimpleServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
            
class TCPAcceptor(threading.Thread):
    allow_reuse_address = True
    def __init__(self, listen_address, listen_port, event_queue):
        threading.Thread.__init__(self)
        self.listen_address = listen_address
        self.listen_port = listen_port
        self.event_queue = event_queue
    def run(self):
        handler = lambda *args: BaremetalLogger(self.event_queue, *args)
        server = SimpleServer((self.listen_address,
                               self.listen_port),
                              handler)
        server.serve_forever()
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser("Log JSON events from network to file")
    parser.add_argument("--listen-address", default="localhost", metavar="ADDR", help="Listen for connections on ADDR")
    parser.add_argument("--listen-port", default=2500, type=int, metavar="PORT", help="Listen for connections on TCP port PORT")
    parser.add_argument("--output", required=True, help="Output filename")
    parser.add_argument("--output-tar-gz", required=True, help="Output tar.gz filename")
    args = parser.parse_args()

    event_queue = queue.Queue()

    TCPAcceptor(args.listen_address,
                args.listen_port,
                event_queue).start()

    with open(args.output, "a+") as log:
        while True:
            msg = event_queue.get()
            assert msg[0] == "data"
            data = msg[1]
            event = {
                "time": time.time()
            }
            try:
                text = data.decode("utf-8")
                if text.startswith("log "):
                    event["type"] = "log"
                    event["message"] = text[len("log "):].rstrip()
                elif text.startswith("exit "):
                    event["type"] = "exit"
                    event["status"] = int(text[len("exit "):])
                elif text.startswith("output "):
                    with open(args.output_tar_gz, "wb+") as f:
                        f.write(base64.b64decode(text[len("output "):].encode("utf-8")))
                    continue
                elif text.startswith("netboot_exit "):
                    event["type"] = "netboot_exit"
                    event["status"] = int(text[len("netboot_exit "):])
                elif text.startswith("keepalive"):
                    event["type"] = "keepalive"
                else:
                    raise Exception("unhandled message")
            except Exception as e:
                event["type"] = "parse-error"
                event["data"] = binascii.hexlify(data).decode("utf-8")
                event["exception"] = str(e)

            log.write(json.dumps(event) + "\n")
            log.flush()
