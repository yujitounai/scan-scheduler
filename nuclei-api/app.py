from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import threading
import uuid
import time
import os
import json

app = Flask(__name__)
CORS(app)

jobs = {}

TEMPLATE_DIR = "/root/nuclei-templates"

@app.route("/nuclei", methods=["POST"])
def run_nuclei_async():
    data = request.json
    target = data.get("target")
    template = data.get("template", os.path.join(TEMPLATE_DIR, "http/exposed-panels/zyxel-router-panel.yaml"))

    if not target:
        return jsonify({"error": "target is required"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "tool": "nuclei",
        "status": "running",
        "submitted_at": time.time(),
        "result": None
    }

    def run():
        try:
            cmd = [
                "nuclei",
                "-u", target,
                "-t", template,
                "-jsonl"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["result"] = {"stderr": result.stderr}
                return
            json_lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.startswith("{")]
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = {"results": json_lines}
        except Exception as e:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["result"] = {"error": str(e)}

    threading.Thread(target=run).start()
    return jsonify({"job_id": job_id}), 202

@app.route("/nuclei/<job_id>", methods=["GET"])
def get_nuclei_result(job_id):
    job = jobs.get(job_id)
    if not job or job["tool"] != "nuclei":
        return jsonify({"error": "Invalid job_id"}), 404
    return jsonify({
        "status": job["status"],
        "result": job["result"]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5557)
