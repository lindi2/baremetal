#!/usr/bin/python3
# gunicorn3 --bind  127.0.0.1:3000 --pythonpath baremetal/server -k flask_sockets.worker 'baremetal_queue_server:app(api_keys=".baremetal_apikeys", queue_dir="queue", config="baremetal/contrib/setup/server.config")'
from flask import Flask
from flask import request
from flask import jsonify
from flask import Response
from flask import abort
from flask_sockets import Sockets
import argparse
import uuid
import re
import os
import json
import sys
import shutil
import threading
import queue
import socket

class UnixSocketReader(threading.Thread):
    def __init__(self, event_queue, socket):
        threading.Thread.__init__(self)
        self.event_queue = event_queue
        self.socket = socket

    def run(self):
        while True:
            try:
                data = self.socket.recv(4096)
            except Exception as e:
                print(f"UnixSocketReader got exception {e}", file=sys.stderr)
                data = b""
            self.event_queue.put((self.socket, data))
            if data == b"":
                break

class WebSocketReader(threading.Thread):
    def __init__(self, event_queue, socket):
        threading.Thread.__init__(self)
        self.event_queue = event_queue
        self.socket = socket

    def run(self):
        while True:
            try:
                data = self.socket.receive()
            except Exception as e:
                print(f"WebSocketReader got exception {e}", file=sys.stderr)
                data = b""
            if data is None:
                data = b""
            elif isinstance(data, bytearray):
                data = bytes(data)
            self.event_queue.put((self.socket, data))
            if data == b"":
                break

def create_app(args, config):
    app = Flask(__name__)
    sockets = Sockets(app)

    with open(args.api_keys) as f:
        apikeys = [x.strip() for x in f.readlines()]

    def check_api_key():
        if request.headers.get("X-API-KEY", "") not in apikeys:
            abort(401)

    def check_job_id(job_id):
        assert job_id == str(uuid.UUID(job_id))

    def get_state(job_id):
        job_dir = os.path.join(args.queue_dir, job_id)
        state_file = os.path.join(job_dir, "state")
        with open(state_file) as f:
            return f.read()
        
    def set_state(job_id, state):
        job_dir = os.path.join(args.queue_dir, job_id)
        state_file = os.path.join(job_dir, "state")
        with open(state_file, "w") as f:
            f.write(state)
            f.flush()
        
    @app.route("/", methods=["POST"])
    def job_create():
        check_api_key()
        if request.json is None:
            abort(400, "JSON body is required")
        if "machine" not in request.json:
            abort(400, "Required parameter machine was not specified")
        if request.json["machine"] not in config["machines"]:
            abort(400, "Requested machine does not exist")
        job_id = str(uuid.uuid4())
        job_dir = os.path.join(args.queue_dir, job_id)
        os.mkdir(job_dir)
        machine_file = os.path.join(job_dir, "machine")
        with open(machine_file, "w") as f:
            f.write(request.json["machine"])
        set_state(job_id, "created")
        print("Created job {}".format(job_id))
        return jsonify({"job_id": job_id})

    @app.route("/<job_id>/upload-chunk/<filetype>", methods=["POST"])
    def job_upload_chunk(job_id=None, filetype=None):
        check_api_key()
        check_job_id(job_id)
        assert get_state(job_id) == "created"
        job_dir = os.path.join(args.queue_dir, job_id)
        if filetype == "image":
            filename = "image.lzo"
        elif filetype == "input":
            filename = "input.tar"
        else:
            abort(400, "Unrecognized file type")
        image_file = os.path.join(job_dir, filename)
        with open(image_file, "ab+") as f:
            f.write(request.get_data())
        return jsonify({"status": get_state(job_id)})

    @app.route("/<job_id>/deploy-template", methods=["POST"])
    def deploy_template(job_id=None):
        check_api_key()
        check_job_id(job_id)
        assert get_state(job_id) == "created"
        if request.json is None:
            abort(400, "JSON body is required")
        if "template" not in request.json:
            abort(400, "Required parameter template was not specified")
        if request.json["template"] not in config["templates"]:
            abort(400, "Requested template does not exist")
        job_dir = os.path.join(args.queue_dir, job_id)
        image_file = os.path.join(job_dir, "image.lzo")
        shutil.copyfile(config["templates"][request.json["template"]]["image"], image_file)
        return jsonify({"status": get_state(job_id)})
    
    @app.route("/<job_id>/start", methods=["POST"])
    def job_start(job_id=None):
        check_api_key()
        check_job_id(job_id)
        assert get_state(job_id) == "created"
        set_state(job_id, "waiting")
        return jsonify({"status": get_state(job_id)})

    @app.route("/<job_id>")
    def job_status(job_id=None):
        check_api_key()
        check_job_id(job_id)
        return jsonify({"status": get_state(job_id)})

    def connect_to_ssh2(web_socket, job_id):
        check_api_key()
        check_job_id(job_id)
        if get_state(job_id) != "started":
            abort(400, "The job has not started yet")

        job_dir = os.path.join(args.queue_dir, job_id)
        ssh_socket_path = os.path.join(job_dir, "ssh.socket")

        print("Opening SSH connection for {}".format(job_id))
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            try:
                unix_socket.connect(ssh_socket_path)
            except FileNotFoundError:
                raise Exception("Internal error, SSH socket is missing")

            event_queue = queue.Queue()
            WebSocketReader(event_queue, web_socket).start()
            UnixSocketReader(event_queue, unix_socket).start()

            while True:
                #print(f"Waiting for events")
                source_socket, data = event_queue.get()
                #print(f"Got {repr(data)} from {source_socket}")

                if source_socket == web_socket:
                    if data == b"C":
                        break
                    else:
                        unix_socket.send(data[1:])
                elif source_socket == unix_socket:
                    if data == b"":
                        web_socket.send(b"C", binary=True)
                        break
                    else:
                        web_socket.send(b"D" + data, binary=True)
        finally:
            unix_socket.close()
        print("Closed SSH connection for {}".format(job_id))

    @sockets.route('/<job_id>/connect-to-ssh')
    def connect_to_ssh(web_socket, job_id=None):
        try:
            connect_to_ssh2(web_socket, job_id)
        except Exception as e:
            web_socket.send(b"EException occured: " + str(e).encode("utf-8"))
        finally:
            web_socket.close()

    @app.route("/<job_id>/results")
    def job_results(job_id=None):
        check_api_key()
        check_job_id(job_id)
        assert get_state(job_id) == "ready"
        job_dir = os.path.join(args.queue_dir, job_id)
        results_file = os.path.join(job_dir, "results.tar")
        with open(results_file, "rb") as f:
            return Response(f.read(), mimetype="application/octet-stream")

    @app.route("/<job_id>/stop", methods=["POST"])
    def job_stop(job_id=None):
        check_api_key()
        check_job_id(job_id)
        job_dir = os.path.join(args.queue_dir, job_id)
        stop_file = os.path.join(job_dir, "stop")
        with open(stop_file, "w+") as f:
            f.write("stop\n")
        return jsonify({"status": "OK"})

    @app.route("/<job_id>", methods=["DELETE"])
    def job_delete(job_id=None):
        check_api_key()
        check_job_id(job_id)
        assert get_state(job_id) == "ready"
        job_dir = os.path.join(args.queue_dir, job_id)
        image_file = os.path.join(job_dir, "image.lzo")
        input_file = os.path.join(job_dir, "input.tar")
        results_file = os.path.join(job_dir, "results.tar")
        state_file = os.path.join(job_dir, "state")
        machine_file = os.path.join(job_dir, "machine")
        stop_file = os.path.join(job_dir, "stop")
        if os.path.exists(input_file):
            os.unlink(input_file)
        if os.path.exists(stop_file):
            os.unlink(stop_file)
        os.unlink(image_file)
        os.unlink(results_file)
        os.unlink(state_file)
        os.unlink(machine_file)
        os.rmdir(job_dir)
        return jsonify({"status": "OK"})

    @app.route("/machines")
    def machines_list():
        check_api_key()
        return jsonify(config["machines"])

    @app.route("/templates")
    def templates_list():
        check_api_key()
        return jsonify(config["templates"])

    return app

def main():
    parser = argparse.ArgumentParser("Receive jobs from HTTP clients and store them in queue directory")
    parser.add_argument("--listen-address", default="127.0.0.1", metavar="ADDRESS", help="Listen on address ADDRESS")
    parser.add_argument("--listen-port", type=int, default=3000, metavar="PORT", help="Listen on TCP port PORT")
    parser.add_argument("--api-keys", metavar="FILE", required=True, help="List of files with valid API keys")
    parser.add_argument("--queue-dir", metavar="DIR", required=True, help="Directory for queue")
    parser.add_argument("--config", required=True, help="Configuration file to use")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    app = create_app(args, config)
    return app

# Gunicorn entry point generator
def app(*args, **kwargs):
    # Gunicorn CLI args are useless.
    # https://stackoverflow.com/questions/8495367/
    #
    # Start the application in modified environment.
    # https://stackoverflow.com/questions/18668947/
    #
    import sys
    sys.argv = ['--gunicorn']
    for k in kwargs:
        sys.argv.append("--" + k.replace("_", "-"))
        sys.argv.append(kwargs[k])
    return main()
    
if __name__ == "__main__":
    app = main()
    app.run(host=args.listen_address, port=args.listen_port)
