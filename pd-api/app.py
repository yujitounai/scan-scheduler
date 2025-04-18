from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import threading
import uuid
import time
import tempfile
import json

app = Flask(__name__)
CORS(app)

jobs = {}

def create_tool_api(tool_name, build_cmd, use_stdin=False):
    @app.route(f"/{tool_name}", methods=["POST"], endpoint=f"{tool_name}_submit")
    def submit_job():
        data = request.json
        target = data.get("target")
        if not target:
            return jsonify({"error": "No target provided"}), 400

        cmd = build_cmd(target)
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "tool": tool_name,
            "status": "running",
            "submitted_at": time.time(),
            "result": None
        }

        def run():
            try:
                result = subprocess.run(
                    cmd,
                    input=target if use_stdin else None,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["result"] = {
                    "stdout": result.stdout.splitlines(),
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            except Exception as e:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["result"] = {"error": str(e)}

        threading.Thread(target=run).start()
        return jsonify({"job_id": job_id}), 202

    @app.route(f"/{tool_name}/<job_id>", methods=["GET"], endpoint=f"{tool_name}_get_result")
    def get_job_result(job_id):
        job = jobs.get(job_id)
        if not job or job["tool"] != tool_name:
            return jsonify({"error": "Invalid job_id"}), 404
        return jsonify({
            "status": job["status"],
            "result": job["result"]
        })

# サブドメイン列挙（引数で渡す）
create_tool_api("subfinder", lambda target: ["subfinder", "-silent", "-d", target])

# httpx は -target 指定可
create_tool_api("httpx", lambda target: ["httpx", "-silent", "-json", "-target", target])

# dnsx, cdncheck は stdin から入力
create_tool_api("dnsx", lambda _: ["dnsx", "-silent", "-a"], use_stdin=True)
create_tool_api("cdncheck", lambda _: ["cdncheck"], use_stdin=True)

# naabu, tlsx は -host 指定
create_tool_api("naabu", lambda target: ["naabu", "-silent", "-host", target])
create_tool_api("tlsx", lambda target: ["tlsx", "-silent", "-host", target])

@app.route("/pipeline", methods=["POST"])
def pipeline_submit():
    data = request.json
    target = data.get("target")
    if not target:
        return jsonify({"error": "No target provided"}), 400

    # ジョブの登録
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "tool": "pipeline",
        "status": "running",
        "submitted_at": time.time(),
        "result": None
    }

    def run_pipeline_job():
        try:
            # Step 1: subfinder
            subfinder_proc = subprocess.run(
                ["subfinder", "-silent", "-d", target],
                capture_output=True,
                text=True,
                timeout=60
            )
            if subfinder_proc.returncode != 0:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["result"] = {"error": "subfinder failed", "stderr": subfinder_proc.stderr}
                return

            subdomains = subfinder_proc.stdout.strip()
            if not subdomains:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["result"] = {"error": "No subdomains found"}
                return

            # Step 2: dnsx
            dnsx_proc = subprocess.run(
                ["dnsx", "-a", "-silent"],
                input=subdomains,
                capture_output=True,
                text=True,
                timeout=60
            )
            if dnsx_proc.returncode != 0:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["result"] = {"error": "dnsx failed", "stderr": dnsx_proc.stderr}
                return

            resolved_hosts = dnsx_proc.stdout.strip()
            if not resolved_hosts:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["result"] = {"error": "No resolvable hosts found"}
                return

            # Step 3: httpx
            httpx_proc = subprocess.run(
                ["httpx", "-silent", "-json"],
                input=resolved_hosts,
                capture_output=True,
                text=True,
                timeout=120
            )
            if httpx_proc.returncode != 0:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["result"] = {"error": "httpx failed", "stderr": httpx_proc.stderr}
                return

            # httpx の出力を JSON として処理
            results = [json.loads(line) for line in httpx_proc.stdout.strip().splitlines()]
            jobs[job_id]["result"] = {"results": results}
            jobs[job_id]["status"] = "completed"

        except Exception as e:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["result"] = {"error": str(e)}

    # バックグラウンドでパイプライン処理を実行
    threading.Thread(target=run_pipeline_job).start()
    return jsonify({"job_id": job_id}), 202

@app.route("/pipeline/<job_id>", methods=["GET"])
def pipeline_get_result(job_id):
    job = jobs.get(job_id)
    if not job or job.get("tool") != "pipeline":
        return jsonify({"error": "Invalid job_id"}), 404
    return jsonify({
        "status": job["status"],
        "result": job["result"]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5556)
