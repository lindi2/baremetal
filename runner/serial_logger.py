#!/usr/bin/python3
import socket
import sys

outputfilename = sys.argv[1]

with open(outputfilename, "wb") as output:
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("10.44.12.1", 2100))
        while True:
            data = s.recv(1024)
            if data == b"":
                break
            output.write(data)
            output.flush()
    
