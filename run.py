import subprocess
import time
import sys
import os
import signal
from multiprocessing import Process


def start_api():
    """Starts the FastAPI application using uvicorn."""
    print("Starting API...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "scraper_os.api.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ]
    )


def start_worker():
    """Starts the Taskiq worker."""
    print("Starting Worker...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "taskiq",
            "worker",
            "scraper_os.infrastructure.queue.broker:broker",
        ]
    )


def check_redis():
    """Simple check to see if redis-server is likely running on default port."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(1)
        s.connect(("127.0.0.1", 6379))
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError):
        return False


if __name__ == "__main__":
    if not os.path.exists(".env"):
        print("Warning: .env file not found. Please create one from .env.example")
        if os.path.exists(".env.example"):
            print("Auto-creating .env from .env.example...")
            with open(".env.example", "r") as f:
                content = f.read()
            with open(".env", "w") as f:
                f.write(content)

    if not check_redis():
        print("Error: Redis is not running on 127.0.0.1:6379.")
        print(
            "Please start Redis using 'docker-compose up -d' before running this script."
        )
        sys.exit(1)

    api_process = Process(target=start_api)
    worker_process = Process(target=start_worker)

    try:
        api_process.start()
        worker_process.start()

        while True:
            time.sleep(1)
            if not api_process.is_alive() or not worker_process.is_alive():
                print("One of the processes died. Shutting down...")
                break
    except KeyboardInterrupt:
        print("\nStopping Atomic Scraper OS...")
    finally:
        api_process.terminate()
        worker_process.terminate()
        api_process.join()
        worker_process.join()
        print("Cleanup complete.")
