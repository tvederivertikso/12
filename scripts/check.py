"""Download, test and publish a filtered proxy subscription."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import pathlib
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request

from parsers import dedupe, expand_subscription, to_xray

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "vpn-sub-checker/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "replace")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_port(port: int, deadline: float) -> bool:
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.05)
    return False


def check_one(uri: str, xray: str, timeout: float) -> tuple[str, bool, str]:
    outbound = to_xray(uri)
    if outbound is None:
        return uri, False, "unsupported"
    port = free_port()
    config = {
        "log": {"loglevel": "none"},
        "inbounds": [{"listen": "127.0.0.1", "port": port, "protocol": "socks", "settings": {"udp": False}}],
        "outbounds": [outbound],
    }
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix="vpn-check-") as directory:
            config_path = pathlib.Path(directory) / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            process = subprocess.Popen(
                [xray, "run", "-c", str(config_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            if not wait_port(port, time.monotonic() + min(timeout, 8)):
                return uri, False, "xray did not open SOCKS"
            result = subprocess.run(
                ["curl", "--silent", "--show-error", "--max-time", str(max(2, int(timeout))),
                 "--proxy", f"socks5h://127.0.0.1:{port}", "-o", os.devnull,
                 "-w", "%{http_code}", "https://www.gstatic.com/generate_204"],
                capture_output=True, text=True, timeout=timeout + 3,
            )
            code = result.stdout.strip()
            return uri, code in {"200", "204", "301", "302"}, f"HTTP {code or 'failed'}"
    except Exception as exc:
        return uri, False, type(exc).__name__
    finally:
        if process is not None and process.poll() is None:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xray", default="xray", help="xray executable")
    parser.add_argument("--limit", type=int, default=0, help="test only first N nodes; 0 means all")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    source_file = ROOT / "sources.txt"
    sources = [line.strip() for line in source_file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    all_uris: list[str] = []
    source_counts: list[tuple[str, int]] = []
    for source in sources:
        try:
            items = expand_subscription(fetch(source))
            all_uris.extend(items)
            source_counts.append((source, len(items)))
        except Exception as exc:
            source_counts.append((source, 0))
            print(f"source failed: {source}: {exc}")
    nodes = dedupe(all_uris)
    if args.limit:
        nodes = nodes[:args.limit]
    print(f"nodes to test: {len(nodes)}")

    results: list[tuple[str, bool, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(check_one, uri, args.xray, args.timeout) for uri in nodes]
        for index, job in enumerate(concurrent.futures.as_completed(jobs), 1):
            result = job.result()
            results.append(result)
            print(f"[{index}/{len(jobs)}] {'OK' if result[1] else 'FAIL'} {result[2]}")

    working = [uri for uri, ok, _ in results if ok]
    previous = OUTPUT / "sub.txt"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    retained = False
    if working:
        previous.write_text("\n".join(working) + "\n", encoding="utf-8")
    elif previous.exists() and previous.read_text(encoding="utf-8").strip():
        retained = True
    report = ["# VPN subscription check", "", f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
              f"- Downloaded unique nodes: {len(nodes)}", f"- Working now: {len(working)}", f"- Previous result retained: {'yes' if retained else 'no'}", "", "## Sources"]
    report.extend(f"- `{url}` — {count} parsed" for url, count in source_counts)
    report += ["", "## Results"]
    report.extend(f"- {'✅' if ok else '❌'} `{detail}` — `{uri[:120]}`" for uri, ok, detail in sorted(results, key=lambda item: not item[1]))
    (OUTPUT / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 0 if working or retained else 1


if __name__ == "__main__":
    raise SystemExit(main())
