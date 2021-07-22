#!/usr/bin/python3
import argparse
import subprocess
import time
import os
import sys
import logging
import tempfile
import json
import socket
import hashlib
import shutil
import pathlib

IMAGE_FILENAME = "/var/www/html/baremetal/baremetal.img.lzo"

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr, level="DEBUG")
logger = logging.getLogger("baremetal")

class Trace:
    def __init__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="baremetal_run_")
        self.processes = []
        self.tcpdump = None
    def __enter__(self):
        tooldir = pathlib.Path(__file__).parent.absolute()
        self.processes.append(subprocess.Popen(["{}/baremetal_logger.py".format(tooldir), "{}/log.json".format(self.tmpdir)]))
        self.processes.append(subprocess.Popen(["{}/serial_logger.py".format(tooldir), "{}/serial.log".format(self.tmpdir)]))
        return self
    def start_network_capture(self):
        self.tcpdump = subprocess.Popen(["sudo", "tcpdump", "-i", "enx0050b607db1f", "-s", "0", "-U", "-w", "{}/network.pcap".format(self.tmpdir)])
    def start_audio_capture(self):
        self.processes.append(subprocess.Popen(["parecord", "--file-format=wav", "--device", "alsa_input.usb-1130_USB_AUDIO-00.analog-mono", "{}/audio.wav".format(self.tmpdir)]))
        self.audio_start_time = time.time()
    def analyze_audio(self):
        tooldir = pathlib.Path(__file__).parent.absolute()
        subprocess.check_call(["{}/extract_beeps.py".format(tooldir), "{}/audio.wav".format(self.tmpdir), str(self.audio_start_time), "{}/audio.json".format(self.tmpdir)])
        os.unlink("{}/audio.wav".format(self.tmpdir))
    def start_video_capture(self):
        tooldir = pathlib.Path(__file__).parent.absolute()
        self.processes.append(subprocess.Popen(["ffmpeg", "-f", "video4linux2", "-s", "1920x1080", "-i", "/dev/video0", "-c:v", "vp8", "{}/video1.webm".format(self.tmpdir)], stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    def netboot_exit_status(self):
        with open("{}/log.json".format(self.tmpdir)) as log:
            for line in log.readlines():
                event = json.loads(line)
                if event["type"] == "netboot_exit":
                    return event["status"]
        return None
    def exit_status(self):
        with open("{}/log.json".format(self.tmpdir)) as log:
            for line in log.readlines():
                event = json.loads(line)
                if event["type"] == "exit":
                    return event["status"]
        return None
    def stop(self):
        for proc in self.processes:
            proc.terminate()
        if self.tcpdump:
            subprocess.call(["sudo", "pkill", "-SIGTERM", "-P", str(self.tcpdump.pid)])
        time.sleep(1)
        for proc in self.processes:
            proc.kill()
        if self.tcpdump:
            subprocess.call(["sudo", "pkill", "-SIGKILL", "-P", str(self.tcpdump.pid)])
            self.tcpdump = None
        self.processes = []
    def save(self, filename):
        subprocess.check_call(["tar", "-C", self.tmpdir, "-c", "-f", args.output, "."])
    def __exit__(self, type, value, traceback):
        self.stop()
        shutil.rmtree(self.tmpdir)
        return False

def get_net_carrier():
    with open("/sys/class/net/enx0050b607db1f/carrier") as f:
        return int(f.read()) != 0
    
def get_net_speed():
    with open("/sys/class/net/enx0050b607db1f/speed") as f:
        return int(f.read())

def set_power(state):
    logger.info("set_power {}".format(state))
    if state:
        while not get_net_carrier():
            logger.debug("calling remote_power")
            subprocess.check_call(["remote_power", "baremetal", "on"])
            time.sleep(1)
    else:
        if get_net_carrier():
            while get_net_carrier():
                logger.debug("calling remote_power")
                subprocess.check_call(["remote_power", "baremetal", "off"])
                time.sleep(1)
        else:
            for i in range(7):
                subprocess.check_call(["remote_power", "baremetal", "off"])
                time.sleep(3)
    logger.debug("set_power {} is done".format(state))

def press_power_button(duration):
    logger.info("press_power_button {}".format(duration))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("10.44.12.1", 2101))
    if duration == 1500:
        s.sendall(b"r")
    elif duration == 6000:
        s.sendall(b"R")
    else:
        assert False
    s.close()
    
def set_image(filename, lzop_compressed):
    logger.info("set_image {}".format(filename))
    if os.path.exists(IMAGE_FILENAME):
        os.unlink(IMAGE_FILENAME)
    if not lzop_compressed:
        subprocess.check_call(["lzop", "-o", IMAGE_FILENAME, filename])
    else:
        shutil.copyfile(filename, IMAGE_FILENAME)

def inject_log_event(buf):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("10.44.12.1", 2500))
    s.sendall(buf.encode("utf-8"))
    s.close()

def send_command(buf):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("10.44.12.2", 9000))
    s.sendall(buf.encode("utf-8"))
    s.close()
    
def set_netboot(state):
    logger.info("set_netboot {}".format(state))
    if state:
        if not os.path.exists("/var/www/html/baremetal/tftp/lpxelinux.0"):
            os.symlink("lpxelinux.0.real",
                       "/var/www/html/baremetal/tftp/lpxelinux.0")
    else:
        if os.path.exists("/var/www/html/baremetal/tftp/lpxelinux.0"):
            os.unlink("/var/www/html/baremetal/tftp/lpxelinux.0")

def sha256(filename):
    with open(filename, "rb") as f:
        h = hashlib.sha256()
        while True:
            data = f.read(1024*1024)
            if data:
                h.update(data)
            else:
                break
        return h.hexdigest()

def restart_services():
    for i in ["isc-dhcp-server", "tftpd-hpa", "ser2net"]:
        subprocess.check_call(["sudo", "systemctl", "stop", i])
    time.sleep(1)
    for i in ["isc-dhcp-server", "tftpd-hpa", "ser2net"]:
        subprocess.check_call(["sudo", "systemctl", "start", i])
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser("Run image on real hardware and return output")
    parser.add_argument("-o", "--output", metavar="TARFILE", required=True, help="Write output to FILE")
    parser.add_argument("--timeout", metavar="SECONDS", default=120, type=int, help="Kill target after SECONDS seconds")
    parser.add_argument("--reboot", action="store_true", help="Use warm reboot instead of cold boot")
    parser.add_argument("--leave-running", action="store_true", help="Leave the target running after the test")
    parser.add_argument("--audio", action="store_true", help="Record audio")
    parser.add_argument("--lzop", action="store_true", help="Image is already lzop compressed")
    parser.add_argument("--video", action="store_true", help="Record video")
    parser.add_argument("image", metavar="FILE", help="Disk image to run")
    args = parser.parse_args()

    restart_services()
    set_power(False)
    with Trace() as t:
        inject_log_event("log Preparing to boot {} (sha256 {})".format(args.image, sha256(args.image)))
        inject_log_event("log Enabling serial logging")
        set_image(args.image, args.lzop)
        inject_log_event("log Enabling network boot service")
        set_netboot(True)
        inject_log_event("log Turning power relay on")
        set_power(True)
        inject_log_event("log Pressing power button for 1500 ms")
        press_power_button(1500)
        while t.netboot_exit_status() == None:
            time.sleep(1)
        assert t.netboot_exit_status() == 0
        if not args.reboot:
            inject_log_event("log Performing shutdown")
            send_command("echo o > /proc/sysrq-trigger")
            time.sleep(1)
            inject_log_event("log Turning power relay off")
            set_power(False)
        inject_log_event("log Disabling network boot service")
        set_netboot(False)
        if args.reboot:
            inject_log_event("log Performing warm reboot")
            send_command("echo b > /proc/sysrq-trigger")
        else:
            inject_log_event("log Turning power relay on")
            set_power(True)
        inject_log_event("log Enabling network packet capture")
        t.start_network_capture()
        if args.video:
            inject_log_event("log Enabling video recording")
            t.start_video_capture()
        if args.audio:
            inject_log_event("log Enabling audio recording")
            t.start_audio_capture()
        if not args.reboot:
            inject_log_event("log Pressing power button for 1500 ms")
            press_power_button(1500)
        start = time.time()
        while t.exit_status() == None:
            if args.timeout and time.time() - start > args.timeout:
                inject_log_event("log Target timed out after {} seconds".format(args.timeout))
                break
            time.sleep(1)
        inject_log_event("log Target exited with status {} in {} seconds".format(t.exit_status(), time.time() - start))
        if args.leave_running:
            logger.info("Keeping the target running as requested")
        else:
            set_power(False)
        t.stop()
        if args.audio:
            t.analyze_audio()
        t.save(args.output)
