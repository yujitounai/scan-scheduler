from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import threading
import uuid
import time

app = Flask(__name__)
CORS(app)

# メモリ内のジョブ管理辞書
jobs = {}

def run_amass_job(job_id, domain):
    cmd = ["amass", "enum", "-d", domain]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["result"] = {"error": str(e)}

@app.route("/amass", methods=["POST"])
def submit_amass_job():
    data = request.json
    target = data.get("target")
    if not target:
        return jsonify({"error": "No target provided"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "running",
        "submitted_at": time.time(),
        "result": None
    }

    thread = threading.Thread(target=run_amass_job, args=(job_id, target))
    thread.start()

    return jsonify({"job_id": job_id}), 202

@app.route("/amass/<job_id>", methods=["GET"])
def get_amass_result(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Invalid job_id"}), 404

    return jsonify({
        "status": job["status"],
        "result": job["result"]
    })

@app.route("/recon", methods=["POST"])
def run_recon():
    data = request.json
    target = data.get("target")
    if not target:
        return jsonify({"error": "No target provided"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "running",
        "submitted_at": time.time(),
        "result": None
    }

    thread = threading.Thread(target=run_recon_job, args=(job_id, target))
    thread.start()

    return jsonify({"job_id": job_id}), 202

def run_recon_job(job_id, target):
    try:
        result = subprocess.run(
            ["python3", "recon_runner.py", target],
            capture_output=True, text=True, timeout=300
        )

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["result"] = {"error": str(e)}

@app.route("/recon/<job_id>", methods=["GET"])
def get_recon_result(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Invalid job_id"}), 404

    return jsonify({
        "status": job["status"],
        "result": job["result"]
    })

@app.route("/nmap", methods=["POST"])
def submit_nmap_job():
    data = request.json
    target = data.get("target")
    if not target:
        return jsonify({"error": "No target provided"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "running",
        "submitted_at": time.time(),
        "result": None
    }

    thread = threading.Thread(target=run_nmap_job, args=(job_id, target))
    thread.start()

    return jsonify({"job_id": job_id}), 202

def run_nmap_job(job_id, target):
    try:
        cmd = ["/usr/bin/nmap", "-sV", target]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["result"] = {"error": str(e)}

@app.route("/nmap/<job_id>", methods=["GET"])
def get_nmap_result(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Invalid job_id"}), 404

    return jsonify({
        "status": job["status"],
        "result": job["result"]
    })

@app.route("/subfinder", methods=["POST"])
def submit_subfinder_job():
    data = request.json
    domain = data.get("domain")
    if not domain:
        return jsonify({"error": "No domain provided"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "running",
        "submitted_at": time.time(),
        "result": None
    }

    thread = threading.Thread(target=run_subfinder_job, args=(job_id, domain))
    thread.start()

    return jsonify({"job_id": job_id}), 202

def run_subfinder_job(job_id, domain):
    try:
        cmd = ["subfinder", "-d", domain, "-silent"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {
            "stdout": result.stdout.splitlines(),
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["result"] = {"error": str(e)}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5555)