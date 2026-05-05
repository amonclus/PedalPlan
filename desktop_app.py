"""
Native desktop wrapper for PedalPlan.
Starts Streamlit in a background process, waits for it to be ready,
then opens a native macOS window (WKWebView) around it.
Closing the window shuts down Streamlit.
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

import webview

PORT = 8501
PROJECT = Path(__file__).parent


def start_streamlit() -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run",
            str(PROJECT / "app.py"),
            f"--server.port={PORT}",
            "--server.headless=true",
            "--server.runOnSave=false",
        ],
        cwd=str(PROJECT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_server(process: subprocess.Popen, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return False  # process died
        try:
            with socket.create_connection(("localhost", PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main():
    process = start_streamlit()

    if not wait_for_server(process):
        log = PROJECT / "streamlit.log"
        print(f"Streamlit failed to start. Check {log}", file=sys.stderr)
        process.terminate()
        sys.exit(1)

    window = webview.create_window(
        title="PedalPlan",
        url=f"http://localhost:{PORT}",
        width=1400,
        height=900,
        min_size=(900, 600),
    )

    def on_closed():
        process.terminate()

    window.events.closed += on_closed

    webview.start()
    process.terminate()


if __name__ == "__main__":
    main()
