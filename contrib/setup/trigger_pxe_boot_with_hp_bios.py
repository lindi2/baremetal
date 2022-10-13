#!/usr/bin/python3
import argparse
import os
import tempfile
import subprocess
import requests
import time
import sys

args = None

class VideoOCR:
    def __init__(self, device, resolution):
        self.device = device
        self.resolution = resolution
    def __enter__(self):
        self.tmpdir = tempfile.mkdtemp("videoocr")
        self.image = os.path.join(self.tmpdir, "image.png")
        cmd = [
            "ffmpeg",
            "-f", "video4linux2",
            "-s", self.resolution,
            "-i", self.device,
            "-loglevel", "warning",
            "-update", "1",
            self.image
        ]
        self.ffmpeg = subprocess.Popen(cmd,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,
                                       stdin=subprocess.DEVNULL)
        return self
    def text(self):
        if not os.path.exists(self.image):
            return ""
        cmd = [
            "tesseract",
            self.image,
            "stdout"
        ]
        try:
            text = subprocess.check_output(cmd, encoding="utf-8", stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("tesseract failed...")
            return ""
        print("####")
        print(repr(text).replace("\\n", "\n"))
        return text
        
    def __exit__(self, type, value, traceback):
        self.ffmpeg.kill()
        outs, errs = self.ffmpeg.communicate()
        if os.path.exists(self.image):
            os.unlink(self.image)
        os.rmdir(self.tmpdir)
        return False

def press(keyname):
    print(f"Pressing {keyname}")
    keymap = {
        "F9": "01m",
        "ESC": "76m",
        "F12": "07m",
        "ENTER": "5Am",
        "DOWN": "72M",
        "A": "1Cm"
        
    }
    code = keymap[keyname]

    params = {
        "code": code
    }
    r = requests.post(args.ps2_url, params=params)

def press_power_button():
    print(f"Pressing power button")
    r = requests.post(args.power_url)

start_time = None
def check_timeout():
    if time.time() - start_time > 100:
        print("Timing out")
        sys.exit(1)
    else:
        time.sleep(1)

    
def main():
    global args
    parser = argparse.ArgumentParser(description="Navigate HP UEFI menus to trigger an IPv4 PXE boot",
                                     epilog="This tool injects PS/2 keyboard events and runs OCR on the HDMI capture output")
    parser.add_argument("--resolution", help="Resolution")
    parser.add_argument("--device", help="Video device")
    parser.add_argument("--ps2-url", help="PS/2 interface url")
    parser.add_argument("--power-url", help="power interface url")
    args = parser.parse_args()


    global start_time
    start_time = time.time()
    with VideoOCR(args.device, args.resolution) as ocr:
        press_power_button()

        while "Boot Menu\n" not in ocr.text():
            print("Waiting for Boot Menu")
            press("F9")
            check_timeout()

        while "Boot Menu\n" in ocr.text():
            print("Trying to exit Boot Menu")
            press("ESC")
            check_timeout()

        while "Network (PXE) Boot (F12)" not in ocr.text():
            print("Waiting for PXE option")
            check_timeout()

        while "Network (PXE) Boot (F12)" in ocr.text():
            print("Choosing PXE option")
            press("F12")
            check_timeout()

        while "Network (PXE) Boot Menu" not in ocr.text():
            print("Waiting for PXE menu")
            check_timeout()

        text = ocr.text()
        if text.find("IPV4 Network") < text.find("IPV6 Network"):
            print("Choosing IPv4")
            press("ENTER")
        else:
            print("Hitting down arrow to choose IPv4")
            press("DOWN")
            time.sleep(0.5)
            press("ENTER")

        while True:
            text = ocr.text()
            print("Waiting for PXE to start")
            if "Start PXE" in text:
                print("PXE boot seems to have started")
                break
            check_timeout()
        
if __name__ == "__main__":
    main()

