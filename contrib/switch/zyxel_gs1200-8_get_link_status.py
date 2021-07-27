#!/usr/bin/python3
import requests
import time
import json
import argparse

parser = argparse.ArgumentParser("Get link status of a port on a Zyxel GS1200-8 switch")
parser.add_argument("--port", type=int, required=True, help="Port number (1-8)")
parser.add_argument("--password-file", required=True, help="File that contains the password")
parser.add_argument("url", help="URL of the switch admin interface")
args = parser.parse_args()

s = requests.session()

with open(args.password_file) as f:
    password = f.read().strip()

url = args.url + "/login.cgi"
data = {
    "password": password
}
headers = {
    "Origin": args.url + "",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
    "Referer": args.url + "/"
}

retries = 0
while True:
    try:
        r = s.post(url, data=data)
        assert r.status_code == 200
        break
    except requests.exceptions.ConnectionError:
        if retries < 3:
            time.sleep(3)
            retries += 1
        else:
            assert False

url = args.url + "/link_data.js"
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
    "Referer": args.url + "/System.html"
}
r = s.get(url, headers=headers)
assert r.status_code == 200
assert "var portstatus" in r.text
text = r.text

url = args.url + "/logout.html"
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
    "Referer": args.url + "/"
}
r = s.get(url, headers=headers)
assert r.status_code == 200

# var portstatus = ['Down','Up','Up','Down','Down','Down','Down','Up','None','None','None'];
prefix = "var portstatus = "
portstatus_line = list(filter(lambda x: x.startswith(prefix), text.split("\n")))[0]
x = json.loads(portstatus_line[len(prefix):-1].replace("'", '"'))
print(x[args.port - 1])


