import psutil
import os


def kill_mcp():
    current_pid = os.getpid()
    fastapi_pid = 32052  # From netstat

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] == "python.exe":
                pid = proc.info["pid"]
                if pid == current_pid or pid == fastapi_pid:
                    continue

                cmdline = proc.info["cmdline"]
                if cmdline and any("mcp_server.py" in arg for arg in cmdline):
                    print(f"Killing MCP PID {pid}: {' '.join(cmdline)}")
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


if __name__ == "__main__":
    kill_mcp()
