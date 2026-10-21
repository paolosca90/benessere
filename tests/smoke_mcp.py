"""Smoke test MCP: avvia il server in stdio, elenca i tool e chiama today_snapshot."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["BENESSERE_DB"] = str(Path(tempfile.mkdtemp()) / "smoke.db")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "mcp_server.py")],
        env={**os.environ, "BENESSERE_DB": os.environ["BENESSERE_DB"]},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("TOOL:", json.dumps(names))

            res = await session.call_tool("today_snapshot", {})
            payload = json.loads(res.content[0].text)
            assert "targets" in payload and "readiness" in payload
            print("SNAPSHOT OK: target_kcal =", payload["targets"]["target_kcal"])

            res = await session.call_tool("list_wods", {})
            wods = json.loads(res.content[0].text)
            assert len(wods) >= 10, f"attesi >=10 WOD seed, trovati {len(wods)}"
            print(f"WOD OK: {len(wods)} nel catalogo")

            res = await session.call_tool(
                "log_wod_result", {"wod": "Fran", "date": "2026-10-20", "score": "4:20"}
            )
            out = json.loads(res.content[0].text)
            assert out["is_pr"] is True
            print("WOD RESULT OK:", out)

            res = await session.call_tool(
                "log_meal", {"meal": "lunch", "kcal": 800, "protein_g": 60}
            )
            assert "registrato" in res.content[0].text
            print("MEAL OK")
            print("SMOKE MCP: PASS")


if __name__ == "__main__":
    asyncio.run(main())
