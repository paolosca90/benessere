"""Vultr private authentication checks. Never print bearer tokens or medical data."""
from __future__ import annotations
import base64
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path

P = Path("/opt/benessere/private")
DASH = "https://dashboard-benessere.45-77-66-215.nip.io/"
MCP = "https://mcp-benessere.45-77-66-215.nip.io/mcp"


def open_url(url, *, headers, data=None):
    req = urllib.request.Request(url, headers=headers, data=data)
    with urllib.request.urlopen(req, timeout=18) as response:
        return response.status, response.read(4096).decode(errors="replace")


def main():
    password = (P / "dashboard_password.txt").read_text().strip()
    basic = base64.b64encode(("benessere:" + password).encode()).decode()
    status, body = open_url(DASH, headers={"Authorization": "Basic " + basic})
    print("Dashboard authenticated:", status, "HTML:", "<html" in body.lower())
    if status != 200 or "<html" not in body.lower():
        raise RuntimeError("Dashboard login failed")

    bearer = (P / "mcp_token.txt").read_text().strip()
    init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2025-06-18",
                                  "capabilities": {}, "clientInfo": {"name": "benessere-smoke", "version": "1"}}}).encode()
    try:
        status, response = open_url(MCP, headers={
            "Authorization": "Bearer " + bearer,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Origin": "https://dashboard-benessere.45-77-66-215.nip.io"}, data=init)
    except urllib.error.HTTPError as err:
        print("MCP initialize HTTP", err.code)
        raise
    print("MCP authenticated initialize:", status, "protocol header present:", "protocolVersion" in response)
    if status != 200 or "protocolVersion" not in response:
        raise RuntimeError("MCP initialize failed")


if __name__ == "__main__":
    main()
