#!/usr/bin/python3
import argparse
import requests
import sys
import time

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Submit image for testing with baremetal_queue_server.py")
    parser.add_argument("-u", "--url", metavar="URL", required="True", help="Service URL")
    parser.add_argument("-o", "--output", metavar="TARFILE", required=True, help="Write output to FILE")
    parser.add_argument("-i", "--input", metavar="TARFILE", help="Provide input files for the execution. ./main will be executed and can write output files to output/")
    parser.add_argument("--chunk-size", default=10, help="Chunk size in MB")
    parser.add_argument("--machine", required=True, help="Machine to use")
    parser.add_argument("--api-key", metavar="FILE", required=True, help="File with API key")
    parser.add_argument("image", metavar="FILE", help="Disk image to run")
    args = parser.parse_args()

    with open(args.api_key) as f:
        apikey = f.read().strip()

    print("Creating new job")
    headers = {
        "X-API-KEY": apikey
    }
    data = {
        "machine": args.machine
    }
    r = requests.post(args.url, headers=headers, json=data)
    if r.status_code != 200:
        print("Server replide with status code {code} and error: {error}".format(code=r.status_code, error=r.text))
        sys.exit(1)
    job_id = r.json()["job_id"]
    print("Job {} was created".format(job_id))

    print("Uploading image in {}MB chunks".format(args.chunk_size))
    chunk = 0
    with open(args.image, "rb") as imagefile:
        while True:
            print("chunk {}".format(chunk))
            data = imagefile.read(args.chunk_size*1024*1024)
            if data == b"":
                break
            url = "{}/{}/upload-chunk/image".format(args.url, job_id)
            r = requests.post(url, headers=headers, data=data)
            assert r.status_code == 200
            chunk += 1

    if args.input:
        print("Uploading input in {}MB chunks".format(args.chunk_size))
        chunk = 0
        with open(args.input, "rb") as inputfile:
            while True:
                print("chunk {}".format(chunk))
                data = inputfile.read(args.chunk_size*1024*1024)
                if data == b"":
                    break
                url = "{}/{}/upload-chunk/input".format(args.url, job_id)
                r = requests.post(url, headers=headers, data=data)
                assert r.status_code == 200
                chunk += 1

    print("Starting job")
    url = "{}/{}/start".format(args.url, job_id)
    r = requests.post(url, headers=headers)
    assert r.status_code == 200

    print("Waiting for job to be ready")
    while True:
        url = "{}/{}".format(args.url, job_id)
        r = requests.get(url, headers=headers)
        assert r.status_code == 200
        status = r.json()["status"]
        print("status {}".format(status))
        if status == "ready":
            break
        time.sleep(15)

    print("Downloading results")
    url = "{}/{}/results".format(args.url, job_id)
    r = requests.get(url, headers=headers)
    assert r.status_code == 200
    with open(args.output, "wb+") as outputfile:
        outputfile.write(r.content)

    print("Deleting job")
    url = "{}/{}".format(args.url, job_id)
    r = requests.delete(url, headers=headers)
    assert r.status_code == 200
