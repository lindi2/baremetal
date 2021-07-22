#!/usr/bin/python3
import socket
import sys
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="localhost", metavar="ADDR", help="Connect to host HOST")
parser.add_argument("--port", required=True, type=int, metavar="PORT", help="Connect to port PORT")
parser.add_argument("--output", required=True, help="Output filename")
args = parser.parse_args()

with open(args.output, "wb") as output:
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((args.host, args.port))
        while True:
            data = s.recv(1024)
            if data == b"":
                break
            output.write(data)
            output.flush()
    
