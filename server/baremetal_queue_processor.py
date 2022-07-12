#!/usr/bin/python3
import argparse
import time
import subprocess
import os
import pathlib
import json

def prepare_image(args):
    tooldir = pathlib.Path(__file__).parent.absolute()
    cwd = os.path.dirname(args.config)
    runner_config = os.path.join(cwd, config["machines"][args.machine]["config"])
    cmd = []
    cmd.append("{}/../runner/baremetal_run.py".format(tooldir))
    cmd.extend(["-o", "/dev/null"])
    cmd.append("--lzop")
    cmd.append("--prepare")
    cmd.append("--reboot")
    cmd.extend(["--target-state", args.target_state])
    cmd.extend(["--config", runner_config])
    cmd.append(args.prepare_image)
    subprocess.call(cmd)

def process_jobs(args):
    processed = 0
    for job_id in os.listdir(args.queue_dir):
        job_dir = os.path.join(args.queue_dir, job_id)
        state_file = os.path.join(job_dir, "state")
        machine_file = os.path.join(job_dir, "machine")
        image_file = os.path.join(job_dir, "image.lzo")
        ssh_socket = os.path.join(job_dir, "ssh.socket")
        input_file = os.path.join(job_dir, "input.tar")
        parameters_file = os.path.join(job_dir, "parameters.json")
        stop_file = os.path.join(job_dir, "stop")
        results_file = os.path.join(job_dir, "results.tar")
        if not os.path.exists(state_file):
            continue
        if not os.path.exists(image_file):
            continue
        if not os.path.exists(parameters_file):
            continue
        with open(state_file) as f:
            if f.read() != "waiting":
                continue
        with open(machine_file) as f:
            machine = f.read()
            if machine != args.machine:
                continue
        with open(parameters_file) as f:
            parameters = json.loads(f.read())
        tooldir = pathlib.Path(__file__).parent.absolute()
        with open(state_file, "w+") as f:
            f.write("started")
        print("Processing {}".format(job_id))
        cwd = os.path.dirname(args.config)
        runner_config = os.path.join(cwd, config["machines"][args.machine]["config"])
        cmd = []
        cmd.append("{}/../runner/baremetal_run.py".format(tooldir))
        cmd.extend(["-o", results_file])
        cmd.extend(["--stop-file", stop_file])
        if parameters.get("video", False):
            cmd.append("--video")
        if parameters.get("reboot", True):
            cmd.append("--reboot")
        if parameters.get("lzop", True):
            cmd.append("--lzop")
        if parameters.get("capture-network", False):
            cmd.append("--capture-network")
        if parameters.get("capture-serial", False):
            cmd.append("--capture-serial")
        if parameters.get("allow-network", False):
            cmd.append("--allow-network")
        cmd.extend(["--ssh-socket", ssh_socket])
        timeout = int(parameters.get("timeout", 300))
        cmd.extend(["--timeout", str(timeout)])
        hard_timeout = int(parameters.get("hard-timeout", 1500))
        cmd.extend(["--hard-timeout", str(hard_timeout)])
        if args.target_state is not None:
            cmd.extend(["--target-state", args.target_state])
        cmd.extend(["--config", runner_config])
        cmd.append(image_file)
        if os.path.exists(input_file):
            cmd.extend(["--input", input_file])
        subprocess.call(cmd)
        with open(state_file, "w+") as f:
            f.write("ready")
        processed += 1
    return processed
        
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser("Process jobs from queue directory")
    parser.add_argument("--queue-dir", metavar="DIR", required=True, help="Directory for queue")
    parser.add_argument("--target-state", metavar="DIR", help="Directory for target state")
    parser.add_argument("--prepare-image", metavar="FILE", help="When idle, prepare FILE for execution")
    parser.add_argument("--config", required=True, help="Server configuration")
    parser.add_argument("--machine", required=True, help="Process only requests for a specific machine")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    image_prepared = False
    while True:
        num_jobs = process_jobs(args)
        if num_jobs == 0:
            if args.target_state is not None and args.prepare_image is not None and not image_prepared:
                prepare_image(args)
                image_prepared = True
            else:
                time.sleep(10)
        else:
            image_prepared = False
