import os
import signal
import subprocess


def kill_mcp():
    try:
        # Get list of processes with mcp_server.py in command line
        output = subprocess.check_output(
            [
                "wmic",
                "process",
                "where",
                'name="python.exe"',
                "get",
                "processid,commandline",
            ],
            text=True,
        )
        lines = output.strip().split("\n")
        for line in lines[1:]:
            if "mcp_server.py" in line:
                pid = line.strip().split()[-1]
                print(f"Killing PID {pid}")
                os.kill(int(pid), signal.SIGTERM)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    kill_mcp()
