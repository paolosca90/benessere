"""Run inside benessere-mcp container; only reads data; never prints health values."""
import asyncio
import os
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    bearer = Path(os.environ["MCP_TOKEN_FILE"]).read_text().strip()
    async with streamablehttp_client(
        "http://127.0.0.1:8000/mcp",
        headers={"Authorization": f"Bearer {bearer}"},
    ) as (reader, writer, _):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            res = await client.list_tools()
            names = [t.name for t in res.tools]
            assert "get_health_overview" in names
            assert "log_meal" in names and "add_wod" in names
            assert "export_all" not in names and "sync_zepp" not in names
            print("MCP tools:", len(names), "safe exposure: yes")
            health = await client.call_tool("get_health_overview", {"days": 3})
            assert not health.isError, "health tool returned error"
            print("MCP get_health_overview: OK")
            day = await client.call_tool("today_snapshot", {})
            assert not day.isError, "snapshot returned error"
            print("MCP today_snapshot: OK")


if __name__ == "__main__":
    asyncio.run(main())
