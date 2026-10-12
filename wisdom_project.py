"""Project-scoped adapter for wisdomGraph 0.3.3; never changes global config."""
import json
import os
from graph_lab import ROOT, settings


def configure():
    import wisdom.connect
    local = ROOT / '.lab'
    local.mkdir(exist_ok=True)
    path = local / 'wisdom-config.json'
    path.write_text(json.dumps({'neo4j_uri':'bolt://127.0.0.1:7691',
        'neo4j_user':'neo4j', 'neo4j_password_env':'GEOTHERMAL_MEMORY_PASSWORD',
        'cache_dir':str(local / 'cache')}))
    # Version-pinned internal adapter: upstream currently hardcodes ~/.wisdom/config.json.
    wisdom.connect._CONFIG_PATH = path
    os.environ['GEOTHERMAL_MEMORY_PASSWORD'] = settings()['LAB_NEO4J_PASSWORD']


if __name__ == '__main__':
    configure()
    from wisdom.mcp import run_mcp_server
    run_mcp_server()
