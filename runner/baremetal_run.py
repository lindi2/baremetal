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

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr, level="DEBUG")
logger = logging.getLogger("baremetal")

class Trace:
    def __init__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="baremetal_run_")
        self.processes = []
        self.tcpdump = None
    def __enter__(self):
        tooldir = pathlib.Path(__file__).parent.absolute()
        self.processes.append(subprocess.Popen(["{}/baremetal_logger.py".format(tooldir), "--listen-port", str(config["log_port"]), "--output-tar-gz", "{}/output.tar.gz".format(self.tmpdir), "--output", "{}/log.json".format(self.tmpdir)]))
        time.sleep(1) # Allow logger to start
        return self
    def start_serial_capture(self):
        tooldir = pathlib.Path(__file__).parent.absolute()
        self.processes.append(subprocess.Popen(["{}/serial_logger.py".format(tooldir), "--port", str(config["serial_port"]), "--output", "{}/serial.log".format(self.tmpdir)]))
    def start_network_capture(self):
        self.tcpdump = subprocess.Popen(["sudo", "ip", "netns", "exec", config["netns"], "tcpdump", "-i", config["iface"], "-s", "0", "-U", "-w", "{}/network.pcap".format(self.tmpdir)], stderr=subprocess.DEVNULL)
    def start_ssh_forward(self, ssh_socket, target_host):
        netns = config["netns"]
        self.processes.append(subprocess.Popen(["socat", f"UNIX-LISTEN:{ssh_socket},fork", f"EXEC:'sudo ip netns exec {netns} socat - TCP-CONNECT:{target_host}:22'"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    def start_audio_capture(self):
        self.processes.append(subprocess.Popen(["parecord", "--file-format=wav", "--device", config["audio_device"], "{}/audio.wav".format(self.tmpdir)]))
        self.audio_start_time = time.time()
    def analyze_audio(self):
        tooldir = pathlib.Path(__file__).parent.absolute()
        subprocess.check_call(["{}/extract_beeps.py".format(tooldir), "{}/audio.wav".format(self.tmpdir), str(self.audio_start_time), "{}/audio.json".format(self.tmpdir)])
        os.unlink("{}/audio.wav".format(self.tmpdir))
    def start_video_capture(self):
        tooldir = pathlib.Path(__file__).parent.absolute()
        self.processes.append(subprocess.Popen(["ffmpeg", "-f", "video4linux2", "-s", config["video_resolution"], "-i", config["video_device"], "-c:v", "vp8", "{}/video.webm".format(self.tmpdir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    def netboot_exit_status(self):
        if args.stop_file is not None and os.path.exists(args.stop_file):
            return -1
        with open("{}/log.json".format(self.tmpdir)) as log:
            for line in log.readlines():
                event = json.loads(line)
                if event["type"] == "netboot_exit":
                    return event["status"]
        return None
    def exit_status(self):
        if args.stop_file is not None and os.path.exists(args.stop_file):
            return -1
        with open("{}/log.json".format(self.tmpdir)) as log:
            for line in log.readlines():
                event = json.loads(line)
                if event["type"] == "exit":
                    return event["status"]
        return None
    def latest_keepalive(self):
        keepalive = None
        with open("{}/log.json".format(self.tmpdir)) as log:
            for line in log.readlines():
                event = json.loads(line)
                if event["type"] == "keepalive":
                    keepalive = event["time"]
        return keepalive
    def latest_scheduled_poweron(self):
        poweron = None
        with open("{}/log.json".format(self.tmpdir)) as log:
            for line in log.readlines():
                event = json.loads(line)
                if event["type"] == "schedule_poweron":
                    poweron = event["time"] + event["delay"]
        return poweron
    def latest_reported_ip_address(self):
        ip = None
        with open("{}/log.json".format(self.tmpdir)) as log:
            for line in log.readlines():
                event = json.loads(line)
                if event["type"] == "report_ip":
                    ip = event["ip"]
        return ip
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
        output_tar_gz = os.path.join(self.tmpdir, "output.tar.gz")
        if os.path.exists(output_tar_gz):
            subprocess.check_call(["tar", "-C", self.tmpdir, "-x", "--no-same-owner", "--no-same-permissions", "--no-acls", "--no-selinux", "--no-xattrs", "--one-top-level", "-z", "-f", output_tar_gz])
            os.unlink(output_tar_gz)
        subprocess.check_call(["tar", "-C", self.tmpdir, "-c", "-f", args.output, "."])
    def __exit__(self, type, value, traceback):
        self.stop()
        shutil.rmtree(self.tmpdir)
        return False

def get_net_carrier():
    tooldir = pathlib.Path(__file__).parent.absolute()
    cmd = config["link_status_command"]
    cwd = os.path.dirname(args.config)
    rc = subprocess.call(cmd, shell=True, cwd=cwd)
    if rc == 0:
        return True
    elif rc == 1:
        return False
    else:
        assert False

def set_power(state):
    logger.info("set_power {}".format(state))
    if state:
        while not get_net_carrier():
            logger.debug("turning power on")
            subprocess.check_call(config["power_on_command"], shell=True)
            time.sleep(1)
    else:
        if get_net_carrier():
            while get_net_carrier():
                logger.debug("turning power off")
                subprocess.check_call(config["power_off_command"], shell=True)
                time.sleep(1)
        else:
            for i in range(3):
                subprocess.check_call(config["power_off_command"], shell=True)
                time.sleep(3)
    logger.debug("set_power {} is done".format(state))

def press_power_button():
    logger.info("press_power_button")
    subprocess.check_call(config["power_button_command"], shell=True)

def start_with_netboot():
    logger.info("start_with_netboot")
    cwd = os.path.dirname(args.config)
    try:
        subprocess.check_call(config["netboot_start_command"], shell=True, cwd=cwd)
        return True
    except subprocess.CalledProcessError:
        return False

def set_agent():
    tooldir = pathlib.Path(__file__).parent.absolute()
    for cmd in ["baremetal-agent", "baremetal"]:
        src = os.path.join(tooldir, cmd)
        dst = os.path.join(config["http_directory"], cmd)
        shutil.copyfile(src, dst)

def set_image(filename, lzop_compressed):
    logger.info("set_image {}".format(filename))
    if os.path.exists(config["image_filename"]):
        os.unlink(config["image_filename"])
    if not lzop_compressed:
        subprocess.check_call(["lzop", "-o", config["image_filename"], filename])
    else:
        shutil.copyfile(filename, config["image_filename"])

def set_input(filename):
    logger.info("set_input {}".format(filename))
    shutil.copyfile(filename, config["input_filename"])

def inject_log_event(buf):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("localhost", config["log_port"]))
    s.sendall(buf.encode("utf-8"))
    s.close()

def send_command(buf):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("localhost", config["control_port"]))
    s.sendall(buf.encode("utf-8"))
    s.close()
    
def set_netboot(state):
    logger.info("set_netboot {}".format(state))
    if state:
        if not os.path.exists(config["netboot_symlink"]):
            os.symlink(config["netboot_symlink_target"],
                       config["netboot_symlink"])
    else:
        if os.path.exists(config["netboot_symlink"]):
            os.unlink(config["netboot_symlink"])

def set_upstream_connection(state):
    subprocess.check_call(["sudo", "ip", "link", "set", config["upstream_iface"], state])

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Run image on real hardware and return output")
    parser.add_argument("-o", "--output", metavar="TARFILE", required=True, help="Write output to FILE")
    parser.add_argument("-i", "--input", metavar="TARFILE", help="Read input from FILE")
    parser.add_argument("--timeout", metavar="SECONDS", type=int, help="Kill target after SECONDS seconds after most recent keepalive")
    parser.add_argument("--hard-timeout", metavar="SECONDS", type=int, help="Kill target after SECONDS seconds")
    parser.add_argument("--reboot", action="store_true", help="Use warm reboot instead of cold boot")
    parser.add_argument("--leave-running", action="store_true", help="Leave the target running after the test")
    parser.add_argument("--audio", action="store_true", help="Record audio")
    parser.add_argument("--capture-network", action="store_true", help="Capture network traffic")
    parser.add_argument("--capture-serial", action="store_true", help="Capture serial traffic")
    parser.add_argument("--allow-network", action="store_true", help="Allow access to Internet during test")
    parser.add_argument("--lzop", action="store_true", help="Image is already lzop compressed")
    parser.add_argument("--video", action="store_true", help="Record video")
    parser.add_argument("--ssh-socket", metavar="SOCKET", help="Listen on unix socket SOCKET for SSH connections")
    parser.add_argument("--stop-file", metavar="FILE", help="Stop job if FILE is created")
    parser.add_argument("--target-state", metavar="DIRECTORY", help="Use DIRECTORY for storing target state")
    parser.add_argument("--prepare", action="store_true", help="Prepare target for execution but do not actually execute payload")
    parser.add_argument("--config", required=True, help="Configuration file")
    parser.add_argument("image", metavar="FILE", help="Disk image to run")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    target_setup_needed = True

    checksum = sha256(args.image)
    if args.target_state:
        state_file = os.path.join(args.target_state, config["name"])
        if os.path.exists(state_file):
            with open(state_file) as f:
                prepared_checksum = f.read()
            if checksum == prepared_checksum:
                logger.info("Reusing previously prepared image")
                target_setup_needed = False

    if target_setup_needed:
        set_power(False)

    if args.prepare and not target_setup_needed:
        logger.info("Target is alread prepared, nothing to do")
        sys.exit(0)

    with Trace() as t:
        if args.capture_serial:
            t.start_serial_capture()
        inject_log_event("log Preparing to boot {} (sha256 {})".format(args.image, sha256(args.image)))
        inject_log_event("log Enabling serial logging")
        if args.allow_network:
            inject_log_event("log Allowing access to Internet during this run")
            set_upstream_connection("up")
        else:
            set_upstream_connection("down")
        set_image(args.image, args.lzop)
        set_agent()
        if args.input:
            set_input(args.input)
        if target_setup_needed:
            inject_log_event("log Enabling network boot service")
            set_netboot(True)
            inject_log_event("log Turning power relay on")
            set_power(True)
            inject_log_event("log Starting the system for netboot")
            if not start_with_netboot():
                inject_log_event("log start_with_netboot failed")
                t.stop()
                t.save(args.output)
                sys.exit(0)
            while t.netboot_exit_status() == None:
                time.sleep(1)
            if t.netboot_exit_status() == -1:
                inject_log_event("log Received command to stop the test")
                set_power(False)
                t.stop()
                t.save(args.output)
                sys.exit(0)
            assert t.netboot_exit_status() == 0
            if args.prepare:
                logging.info("Preparing target for image is complete")
                with open(state_file, "w+") as f:
                    f.write(checksum)
                    t.stop()
                    sys.exit(0)
        else:
            os.unlink(state_file)

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
        if args.capture_network:
            inject_log_event("log Enabling network packet capture")
            t.start_network_capture()
        if args.video:
            inject_log_event("log Enabling video recording")
            t.start_video_capture()
        if args.audio:
            inject_log_event("log Enabling audio recording")
            t.start_audio_capture()
        if not args.reboot:
            inject_log_event("log Pressing power button")
            press_power_button()
        start = time.time()
        latest_keepalive = time.time()
        latest_poweron = time.time()
        ssh_socket_started = False
        while t.exit_status() == None:
            if args.hard_timeout and time.time() - start > args.hard_timeout:
                inject_log_event("log Target timed out after {} seconds (hard timeout)".format(args.hard_timeout))
                break
            keepalive = t.latest_keepalive()
            if keepalive and keepalive > latest_keepalive:
                latest_keepalive = keepalive
            poweron = t.latest_scheduled_poweron()
            if poweron and poweron > latest_poweron and poweron < time.time():
                inject_log_event("log Pressing power button as scheduled")
                press_power_button()
                latest_poweron = poweron
            if args.ssh_socket and not ssh_socket_started:
                latest_reported_ip = t.latest_reported_ip_address()
                if latest_reported_ip is not None:
                    t.start_ssh_forward(args.ssh_socket, latest_reported_ip)
                    ssh_socket_started = True

            if args.timeout and time.time() - latest_keepalive > args.timeout:
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
