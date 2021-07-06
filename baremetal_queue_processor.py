#!/usr/bin/python3
import argparse
import time
import subprocess
import os
import pathlib

def process_jobs(args):
    processed = 0
    for job_id in os.listdir(args.queue_dir):
        job_dir = os.path.join(args.queue_dir, job_id)
        state_file = os.path.join(job_dir, "state")
        image_file = os.path.join(job_dir, "image.lzo")
        results_file = os.path.join(job_dir, "results.tar")
        if not os.path.exists(state_file):
            continue
        if not os.path.exists(image_file):
            continue
        with open(state_file) as f:
            if f.read() != "waiting":
                continue
        tooldir = pathlib.Path(__file__).parent.absolute()
        with open(state_file, "w+") as f:
            f.write("started")
        print("Processing {}".format(job_id))
        subprocess.call(["{}/baremetal_run.py".format(tooldir),
                         "-o",
                         results_file,
                         "--audio",
                         "--video",
                         "--lzop",
                         image_file])
        with open(state_file, "w+") as f:
            f.write("ready")
        processed += 1
    return processed
        
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser("Process jobs from queue directory")
    parser.add_argument("--queue-dir", metavar="DIR", required=True, help="Directory for queue")
    args = parser.parse_args()

    while True:
        num_jobs = process_jobs(args)
        if num_jobs == 0:
            time.sleep(10)
