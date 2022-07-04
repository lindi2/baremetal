#!/usr/bin/python3
import argparse
import requests
import sys
import time
import signal

def sigint_handler(signum, frame):
    print("Stopping job {}".format(job_id))
    url = "{}/{}/stop".format(args.url, job_id)
    r = requests.post(url, headers=headers)
    if r.status_code != 200:
        print("Stopping job failed with code {}: {}".format(r.status_code, r.text))
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Submit image for testing with baremetal_queue_server.py")
    parser.add_argument("-u", "--url", metavar="URL", required="True", help="Service URL")
    parser.add_argument("-o", "--output", metavar="TARFILE", help="Write output to FILE")
    parser.add_argument("--save-websocket-url", metavar="FILE", help="Save websocket URL to FILE")
    parser.add_argument("-i", "--input", metavar="TARFILE", help="Provide input files for the execution. ./main will be executed and can write output files to output/")
    parser.add_argument("--chunk-size", default=10, help="Chunk size in MB")
    parser.add_argument("--machine", help="Machine to use")
    parser.add_argument("--list-templates", action="store_true", help="List available templates")
    parser.add_argument("--list-machines", action="store_true", help="List available machines")
    parser.add_argument("--api-key", metavar="FILE", required=True, help="File with API key")
    parser.add_argument("--template", metavar="TEMPLATE", help="Use template TEMPLATE instead of uploading an image")
    parser.add_argument("--image", metavar="FILE", help="Disk image to run")
    parser.add_argument("--timeout", default=300, metavar="SECONDS", type=int, help="Kill target after SECONDS seconds after most recent keepalive")
    parser.add_argument("--hard-timeout", default=1500, metavar="SECONDS", type=int, help="Kill target after SECONDS seconds after most recent keepalive")
    parser.add_argument("--cold-boot", action="store_true", help="Use cold boot instead of warm boot")
    parser.add_argument("--allow-network", action="store_true", help="Allow access to Internet during test")
    parser.add_argument("--video", action="store_true", help="Record video")

    args = parser.parse_args()

    with open(args.api_key) as f:
        apikey = f.read().strip()

    parameters = {
        "video": args.video,
        "reboot": not args.cold_boot,
        "lzop": True,
        "allow-network": args.allow_network,
        "timeout": args.timeout,
        "hard-timeout": args.hard_timeout
    }

    headers = {
        "X-API-KEY": apikey
    }

    if args.list_machines:
        url = "{}/machines".format(args.url)
        r = requests.get(url, headers=headers)
        assert r.status_code == 200
        for machine in r.json().keys():
            name = r.json()[machine]["name"]
            print(f"{machine}: {name}")
            for capability in r.json()[machine]["capabilities"].keys():
                capability_value = r.json()[machine]["capabilities"][capability]
                print(f" - {capability}: {capability_value}")
        sys.exit(1)

    if args.list_templates:
        url = "{}/templates".format(args.url)
        r = requests.get(url, headers=headers)
        assert r.status_code == 200
        for template in r.json().keys():
            description = r.json()[template]["description"]
            print(f"{template}: {description}")
        sys.exit(1)

    if not args.machine:
        print("No --machine was specified. Please use --list-machines to select one")
        sys.exit(1)

    if not args.image and not args.template:
        print("You need to specify either --image or --template")
        sys.exit(1)

    if not args.output:
        print("You need to specify --output")
        sys.exit(1)


    print("Creating new job")
    data = {
        "machine": args.machine,
        "parameters": parameters,
    }
    r = requests.post(args.url, headers=headers, json=data)
    if r.status_code != 200:
        print("Server replied with status code {code} and error: {error}".format(code=r.status_code, error=r.text))
        sys.exit(1)
    job_id = r.json()["job_id"]
    print("Job {} was created".format(job_id))

    if args.image:
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

    if args.template:
        print(f"Deploying template {args.template}")
        data = {
            "template": args.template
        }
        url = "{}/{}/deploy-template".format(args.url, job_id)
        r = requests.post(url, headers=headers, json=data)
        if r.status_code != 200:
            print("Server replied with status code {code} and error: {error}".format(code=r.status_code, error=r.text))
            sys.exit(1)

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

    signal.signal(signal.SIGINT, sigint_handler)

    print("Starting job")
    url = "{}/{}/start".format(args.url, job_id)
    r = requests.post(url, headers=headers)
    assert r.status_code == 200

    print("Waiting for job to be ready")
    prev_status = None
    while True:
        url = "{}/{}".format(args.url, job_id)
        r = requests.get(url, headers=headers)
        assert r.status_code == 200
        status = r.json()["status"]
        print("status {}".format(status))
        if status != prev_status and status == "started":
            web_socket_base = args.url.replace("http://", "ws://").replace("https://", "wss://")
            web_socket_base_url = f"{web_socket_base}/{job_id}"
            if args.save_websocket_url:
                with open(args.save_websocket_url, "w+") as f:
                    f.write(web_socket_base_url)
            print(f"""You can connect to the target using SSH as follows:

ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o "proxycommand ./baremetal_ssh_proxy.py -a {args.api_key} {web_socket_base_url}" user@dummy

""")
        if status == "ready":
            break
        time.sleep(15)
        prev_status = status

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
