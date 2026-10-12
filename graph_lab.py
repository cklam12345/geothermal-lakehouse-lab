"""Build a typed geothermal graph and separate WisdomGraph memory from synthetic data."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import secrets

from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / 'ontology.json').read_text())


def init():
    path = ROOT / '.env'
    if not path.exists():
        # Exclusive creation; never overwrite an existing database password.
        with path.open('x') as stream:
            path.chmod(0o600)
            stream.write('LAB_NEO4J_PASSWORD=' + secrets.token_urlsafe(24) + '\n')
    print('Local credentials ready in .env (ignored by git).')


def settings():
    values = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines()
                  if line and not line.startswith('#'))
    return values


def driver(port):
    return GraphDatabase.driver(f'bolt://127.0.0.1:{port}',
                               auth=('neo4j', settings()['LAB_NEO4J_PASSWORD']))


def make_graph():
    nodes, edges = {}, []

    def node(key, kind, title, **props):
        nodes[key] = dict(id=key, kind=kind, title=title, **{'synthetic': True, **props})
        return key

    def edge(source, relation, target, **props):
        edges.append(dict(source=source, relation=relation, target=target, **props))

    for name, spec in SCHEMA['classes'].items():
        node('class:' + name, 'Class', name, definition=spec['definition'], synthetic=False)
        if 'parent' in spec:
            edge('class:' + name, 'SUBCLASS_OF', 'class:' + spec['parent'])

    data = ROOT / 'data/synthetic_wells.csv'
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    dataset = node('dataset:' + digest, 'SourceDataset', 'Synthetic wells CSV',
                   path='data/synthetic_wells.csv', sha256=digest, storage='Local CSV; Delta migration not implemented')
    for property_name, unit in [('temperature', 'degC'), ('mass_flow', 'kg/s')]:
        node('property:' + property_name, 'ObservableProperty', property_name, measurement_location='unknown')
        node('unit:' + unit, 'Unit', unit)
    for row_number, row in enumerate(csv.DictReader(data.read_text().splitlines()), start=2):
        wid = row['well_id']
        well = node('well:' + wid, 'Well', wid)
        site = node('site:' + row['site'], 'Site', row['site'])
        reservoir = node('reservoir:' + row['site'], 'Reservoir', row['site'] + ' reservoir',
                         assertion_basis='Invented demo grouping; not inferred from geology')
        edge(well, 'LOCATED_AT', site)
        edge(well, 'ASSIGNED_TO', reservoir, assertion_basis='Synthetic fixture')
        record = node(f'record:{digest}:{row_number}', 'SourceRecord', f'CSV line {row_number}',
                      source_row=row_number, raw_record=json.dumps(row))
        edge(record, 'PART_OF', dataset)
        problems = []
        for column, prop, unit in [('temperature_c', 'temperature', 'degC'), ('flow_kg_s', 'mass_flow', 'kg/s')]:
            try:
                value = float(row[column])
                if not math.isfinite(value):
                    raise ValueError('nonfinite')
            except ValueError:
                problems.append(f'{column}: missing or nonnumeric/nonfinite')
                continue
            valid = 0 < value <= 400 if prop == 'temperature' else value > 0
            if not valid:
                problems.append(f'{column}: outside toy quality bounds')
            obs = node(f'obs:{digest}:{row_number}:{prop}', 'Observation', f'{wid}: {value:g} {unit}',
                       value=value, quality='accepted' if valid else 'rejected',
                       observed_at='unknown', measurement_location='unknown', source_row=row_number)
            edge(obs, 'ABOUT', well)
            edge(obs, 'MEASURES', 'property:' + prop)
            edge(obs, 'HAS_UNIT', 'unit:' + unit)
            edge(obs, 'SOURCED_FROM', record)
        if problems:
            issue = node(f'issue:{digest}:{row_number}', 'QualityIssue', wid + ': quality issue',
                         reason='; '.join(problems))
            edge(issue, 'FLAGS', record)
    for key, item in list(nodes.items()):
        if item['kind'] != 'Class':
            edge(key, 'INSTANCE_OF', 'class:' + item['kind'])
    return dict(version=SCHEMA['version'], status=SCHEMA['status'], nodes=list(nodes.values()), edges=edges)


def validate(graph):
    nodes = {n['id']: n for n in graph['nodes']}
    assert len(nodes) == len(graph['nodes']), 'duplicate node IDs'
    triples = set()
    for e in graph['edges']:
        assert e['source'] in nodes and e['target'] in nodes, 'dangling edge'
        triple = (e['source'], e['relation'], e['target'])
        assert triple not in triples, 'duplicate edge'
        triples.add(triple)
        a, b = nodes[e['source']], nodes[e['target']]
        if e['relation'] == 'SUBCLASS_OF':
            assert a['kind'] == b['kind'] == 'Class'
        elif e['relation'] == 'INSTANCE_OF':
            assert b['id'] == 'class:' + a['kind']
        else:
            assert [a['kind'], b['kind']] == SCHEMA['relationships'][e['relation']], 'invalid domain/range'
    for n in nodes.values():
        required = ('ABOUT', 'MEASURES', 'HAS_UNIT', 'SOURCED_FROM') if n['kind'] == 'Observation' else ()
        if n['kind'] == 'SourceRecord':
            required = ('PART_OF',)
        for relation in required:
            assert sum(e['source'] == n['id'] and e['relation'] == relation for e in graph['edges']) == 1
    return graph


def seed_domain(graph):
    with driver(7690) as db:
        db.verify_connectivity()
        with db.session(database='neo4j') as s:
            s.run('CREATE CONSTRAINT geo_id IF NOT EXISTS FOR (n:GeoEntity) REQUIRE n.id IS UNIQUE').consume()
            def write(tx):
                for n in graph['nodes']:
                    kind = n['kind']
                    assert kind in SCHEMA['classes'] or kind == 'Class'
                    tx.run(f'MERGE (n:GeoEntity:{kind} {{id:$id}}) SET n += $props', id=n['id'], props=n).consume()
                for e in graph['edges']:
                    relation = e['relation']
                    assert relation in SCHEMA['relationships'] or relation in ('INSTANCE_OF', 'SUBCLASS_OF')
                    tx.run(f'MATCH (a:GeoEntity {{id:$source}}),(b:GeoEntity {{id:$target}}) '
                           f'MERGE (a)-[r:{relation}]->(b) SET r += $props',
                           source=e['source'], target=e['target'],
                           props={k:v for k,v in e.items() if k not in ('source','target','relation')}).consume()
            s.execute_write(write)


def seed_memory():
    from wisdom.connect import ensure_schema
    from wisdom.merge import merge_extraction
    with driver(7691) as db:
        ensure_schema(db)
        extraction = {'nodes': [
            {'id':'geo-lab:scope:v1', 'label':'Geothermal prototype scope', 'tier':'knowledge',
             'content':'All wells are synthetic. This proposed ontology needs domain-expert review. No Databricks connection is implemented.',
             'source_file':'ontology.json'},
            {'id':'geo-lab:separation:v1', 'label':'Separate domain facts from agent memory', 'tier':'experience',
             'content':'This project uses separate Neo4j containers and volumes for domain records and WisdomGraph memory. Cross-store references use stable IDs, not physical graph edges.',
             'source_file':'compose.yaml'},
            {'id':'geo-lab:measurement-context:v1', 'label':'Do not infer measurement context', 'tier':'knowledge',
             'content':'The CSV has no measurement time or location/depth. Never equate its temperature with reservoir temperature or claim commercial viability.',
             'source_file':'data/synthetic_wells.csv'}], 'edges': []}
        # No reinforcement edges are replayed: wisdomGraph increments their weight on MERGE.
        with db.session() as s:
            s.execute_write(lambda tx: merge_extraction(tx, extraction,
                            source_uri='repo:geothermal-lakehouse-lab/ontology.json@0.1.0', project='geothermal-lakehouse-lab'))
    print('Seeded project memory using wisdomGraph.merge.merge_extraction().')


def export(graph):
    out = ROOT / 'output'
    out.mkdir(exist_ok=True)
    (out / 'domain-graph.json').write_text(json.dumps(graph, indent=2))
    template = (ROOT / 'graph_view.html').read_text()
    (out / 'geothermal-graph.html').write_text(template.replace('__GRAPH_DATA__', json.dumps(graph).replace('<','\\u003c')))
    print('Graph viewer: output/geothermal-graph.html')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init','build','export'])
    args = parser.parse_args()
    if args.command == 'init':
        init()
        return
    graph = validate(make_graph())
    if args.command == 'build':
        seed_domain(graph)
        seed_memory()
    export(graph)
    print(f"Validated {len(graph['nodes'])} nodes and {len(graph['edges'])} relationships.")


if __name__ == '__main__':
    main()
