#!/usr/bin/python3
from flask import Flask
from flask import request
from flask import jsonify
from flask import Response
from flask import abort
import argparse
import uuid
import re
import os
import json

def create_app(args):
    app = Flask(__name__)

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

    @app.route("/<job_id>/results")
    def job_results(job_id=None):
        check_api_key()
        check_job_id(job_id)
        assert get_state(job_id) == "ready"
        job_dir = os.path.join(args.queue_dir, job_id)
        results_file = os.path.join(job_dir, "results.tar")
        with open(results_file, "rb") as f:
            return Response(f.read(), mimetype="application/octet-stream")

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
        if os.path.exists(input_file):
            os.unlink(input_file)
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

    return app

if __name__ == "__main__":
    parser = argparse.ArgumentParser("Receive jobs from HTTP clients and store them in queue directory")
    parser.add_argument("--listen-address", default="127.0.0.1", metavar="ADDRESS", help="Listen on address ADDRESS")
    parser.add_argument("--listen-port", type=int, default=3000, metavar="PORT", help="Listen on TCP port PORT")
    parser.add_argument("--api-keys", metavar="FILE", required=True, help="List of files with valid API keys")
    parser.add_argument("--queue-dir", metavar="DIR", required=True, help="Directory for queue")
    parser.add_argument("--config", required=True, help="Configuration file to use")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    app = create_app(args)
    app.run(host=args.listen_address, port=args.listen_port)
    
    
