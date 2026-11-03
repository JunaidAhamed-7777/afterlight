"""Small loopback client for the pinned Blender MCP JSON bridge.

python assets/src/blender_mcp.py --script assets/src/generate_city_v4.py
"""
import argparse
import json
from pathlib import Path
import socket


def command(kind, params=None, port=9876, timeout=600):
    with socket.create_connection(("127.0.0.1", port), 5) as sock:
        sock.settimeout(timeout)
        sock.sendall(json.dumps({"type": kind, "params": params or {}}).encode())
        data = bytearray()
        while True:
            packet = sock.recv(65536)
            if not packet:
                raise RuntimeError("Blender MCP disconnected before returning a complete response")
            data.extend(packet)
            if len(data) > 16 * 1024 * 1024:
                raise RuntimeError("Blender MCP response exceeds 16 MiB")
            try:
                result = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if result.get("status") == "error":
                raise RuntimeError(result.get("message", result))
            return result.get("result", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path)
    parser.add_argument("--code")
    parser.add_argument("--port", type=int, default=9876)
    args = parser.parse_args()
    if args.script:
        path = args.script.resolve()
        source = path.read_text(encoding="utf-8")
        code = "exec(compile(" + repr(source) + "," + repr(str(path)) + ",'exec')," + repr({"__file__": str(path), "__name__": "__main__"}) + ")"
    else:
        code = args.code
    result = command("execute_code", {"code": code}, args.port) if code else command("get_scene_info", port=args.port)
    print(result.get("result", json.dumps(result, indent=2)))
