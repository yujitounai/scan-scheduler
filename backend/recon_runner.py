import subprocess
import json
import sys

def run_recon(domain):
    script = f"""
workspaces load default
marketplace install recon/domains-hosts/brute_hosts
modules load recon/domains-hosts/brute_hosts
options set SOURCE bogus.jp
run
show hosts
exit
"""

    result = subprocess.run(
        ['recon-ng'],
        input=script,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing domain"}))
        sys.exit(1)

    res = run_recon(sys.argv[1])
    print(json.dumps(res, indent=2))

