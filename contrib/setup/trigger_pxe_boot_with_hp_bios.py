#!/usr/bin/python3
import argparse
import os
import tempfile
import subprocess
import requests
import time

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
        self.ffmpeg = subprocess.Popen(cmd)
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
        print(text)
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
        "DOWN": "72M"
        
    }
    code = keymap[keyname]

    params = {
        "code": code
    }
    r = requests.post(args.ps2_url, params=params)

def press_power_button():
    print(f"Pressing power button")
    r = requests.post(args.power_url)
    
def main():
    global args
    parser = argparse.ArgumentParser(description="Navigate HP UEFI menus to trigger an IPv4 PXE boot",
                                     epilog="This tool injects PS/2 keyboard events and runs OCR on the HDMI capture output")
    parser.add_argument("--resolution", help="Resolution")
    parser.add_argument("--device", help="Video device")
    parser.add_argument("--ps2-url", help="PS/2 interface url")
    parser.add_argument("--power-url", help="power interface url")
    args = parser.parse_args()


    with VideoOCR(args.device, args.resolution) as ocr:
        press_power_button()

        while "Boot Menu" not in ocr.text():
            press("F9")
            time.sleep(1)

        press("ESC")

        while "Network (PXE) Boot (F12)" not in ocr.text():
            time.sleep(1)

        press("F12")

        while "Network (PXE) Boot Menu" not in ocr.text():
            time.sleep(1)

        text = ocr.text()
        if text.find("IPV4 Network") < text.find("IPV6 Network"):
            press("ENTER")
        else:
            press("DOWN")
            time.sleep(0.5)
            press("ENTER")

        while True:
            text = ocr.text()
            if "Start PXE" in text:
                # Ensure we are booting with IPv4 and not IPv6
                assert "4" in text
                break
        
if __name__ == "__main__":
    main()

