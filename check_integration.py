"""Explicit live checks against only this lab's two local databases."""
import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from graph_lab import ROOT, driver, make_graph, seed_domain, seed_memory


def counts(port):
    with driver(port) as db, db.session() as s:
        return (s.run('MATCH (n) RETURN count(n) AS c').single()['c'],
                s.run('MATCH ()-[r]->() RETURN count(r) AS c').single()['c'])


async def main():
    before = (counts(7690), counts(7691))
    seed_domain(make_graph())
    seed_memory()
    after = (counts(7690), counts(7691))
    assert before == after, (before, after)
    with driver(7690) as db, db.session() as s:
        assert s.run("MATCH (n) WHERE 'Knowledge' IN labels(n) OR 'Experience' IN labels(n) RETURN count(n) AS c").single()['c'] == 0
        assert s.run('MATCH (n:GeoEntity) RETURN count(n) AS c').single()['c'] == 48
    with driver(7691) as db, db.session() as s:
        assert s.run("MATCH (n) WHERE 'GeoEntity' IN labels(n) RETURN count(n) AS c").single()['c'] == 0
        assert s.run('MATCH (n:Knowledge) RETURN count(n) AS c').single()['c'] == 2
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'wisdom_project.py')])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = await client.list_tools()
            assert 'wisdom_query' in [t.name for t in tools.tools]
            status = await client.call_tool('wisdom_status', {})
            assert not status.isError, status
            print('MCP handshake and wisdom_status passed; tools:', len(tools.tools))
    print('Repeat-import counts stable; stores isolated:', after)


if __name__ == '__main__':
    asyncio.run(main())
