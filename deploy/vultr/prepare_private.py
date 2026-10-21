"""One-time provisioning on Vultr. Run as root; secrets never printed.

Only writes the private Benessere directory and adds two virtual hosts to
the existing Caddyfile; never stops or deletes YouTubeCreatorOS services.
"""
from __future__ import annotations
import os
import secrets
import shutil
import subprocess
from pathlib import Path

BASE = Path("/opt/benessere")
PRIVATE = BASE / "private"
CADDYFILE = Path("/opt/youtubecreatoros/app/Caddyfile")
TEMPLATE = BASE / "source/deploy/vultr/dashboard.Caddyfile"
DASH_HOST = "dashboard-benessere.45-77-66-215.nip.io"
MCP_HOST = "mcp-benessere.45-77-66-215.nip.io"

def create_secret(name: str, owner_uid: int, owner_gid: int) -> str:
    path = PRIVATE / name
    if not path.exists():
        token = secrets.token_urlsafe(32)
        with path.open("x", encoding="utf-8") as f:
            f.write(token + "\n")
    else:
        token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError(f"Invalid existing secret file: {name}")
    os.chown(path, owner_uid, owner_gid)
    os.chmod(path, 0o400)
    return token

def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run as root")
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(PRIVATE, 0o700)
    pwd = create_secret("dashboard_password.txt", 0, 0)
    create_secret("mcp_token.txt", 10001, 10001)
    raw = CADDYFILE.read_text(encoding="utf-8")
    if DASH_HOST in raw or MCP_HOST in raw:
        if DASH_HOST not in raw or MCP_HOST not in raw:
            raise RuntimeError("Caddy configuration partially present; inspect it")
        print("Caddy virtual hosts already present")
        return
    result = subprocess.run(
        ["docker", "exec", "youtube-creator-os-caddy",
         "caddy", "hash-password", "--plaintext", pwd],
        check=True, capture_output=True, text=True,
    )
    digest = result.stdout.strip()
    if not digest.startswith("$2"):
        raise RuntimeError("Unrecognized Caddy bcrypt digest")
    extra = TEMPLATE.read_text(encoding="utf-8").replace("__DASHBOARD_BCRYPT_HASH__", digest)
    backup = CADDYFILE.with_name("Caddyfile.backup-before-benessere-web")
    shutil.copy2(CADDYFILE, backup)
    with CADDYFILE.open("a", encoding="utf-8") as f:
        f.write("\n" + extra)
    print("Benessere dashboard and MCP Caddy virtual hosts prepared (not yet applied).")
    print("Secrets saved in private files; never print them in logs.")

if __name__ == "__main__":
    main()
