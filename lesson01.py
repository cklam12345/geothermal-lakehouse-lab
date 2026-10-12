"""Local medallion-pattern exercise. SQLite is a teaching aid, not a lakehouse."""

import argparse
import csv
import math
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def validate(row):
    """Toy quality contract; these bounds are not geothermal engineering rules."""
    if not row['well_id'].strip() or not row['site'].strip():
        return None, 'missing well ID or site'
    try:
        temperature = float(row['temperature_c'])
        flow = float(row['flow_kg_s'])
    except ValueError:
        return None, 'missing or nonnumeric measurement'
    if not all(math.isfinite(value) for value in (temperature, flow)):
        return None, 'nonfinite measurement'
    if not (0 < temperature <= 400) or flow <= 0:
        return None, 'outside toy quality bounds'
    return (row['well_id'].strip(), row['site'].strip(), temperature, flow), None


def build(connection):
    # Only recreate this lesson's generated tables. The source CSV is untouched.
    connection.executescript('''
        DROP TABLE IF EXISTS bronze_wells;
        DROP TABLE IF EXISTS silver_wells;
        DROP TABLE IF EXISTS rejected_wells;
        CREATE TABLE bronze_wells (
            source_row INTEGER, well_id TEXT, site TEXT,
            temperature_c TEXT, flow_kg_s TEXT
        );
        CREATE TABLE silver_wells (
            source_row INTEGER, well_id TEXT UNIQUE, site TEXT,
            temperature_c REAL, flow_kg_s REAL
        );
        CREATE TABLE rejected_wells (source_row INTEGER, well_id TEXT, reason TEXT);
    ''')
    seen = set()
    with (ROOT / 'data/synthetic_wells.csv').open(newline='') as source:
        for source_row, row in enumerate(csv.DictReader(source), start=2):
            connection.execute(
                'INSERT INTO bronze_wells VALUES (?, ?, ?, ?, ?)',
                (source_row, row['well_id'], row['site'], row['temperature_c'], row['flow_kg_s']),
            )
            cleaned, reason = validate(row)
            if cleaned is not None and cleaned[0] in seen:
                reason = 'duplicate well ID; first valid row retained'
            if reason:
                connection.execute('INSERT INTO rejected_wells VALUES (?, ?, ?)',
                                   (source_row, row['well_id'], reason))
            else:
                seen.add(cleaned[0])
                connection.execute('INSERT INTO silver_wells VALUES (?, ?, ?, ?, ?)',
                                   (source_row, *cleaned))
    connection.commit()


def screen(connection, min_temperature, min_flow):
    # Gold: an explicitly defined application question, answered from validated data.
    return connection.execute('''
        SELECT well_id, site, temperature_c, flow_kg_s, source_row
        FROM silver_wells
        WHERE temperature_c >= ? AND flow_kg_s >= ?
        ORDER BY well_id
    ''', (min_temperature, min_flow)).fetchall()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--min-temperature', type=float, default=180)
    parser.add_argument('--min-flow', type=float, default=30)
    args = parser.parse_args()
    if not all(math.isfinite(v) for v in (args.min_temperature, args.min_flow)):
        parser.error('thresholds must be finite')
    (ROOT / 'output').mkdir(exist_ok=True)
    with sqlite3.connect(ROOT / 'output/lesson01.sqlite') as connection:
        build(connection)
        print('SYNTHETIC DATA — classroom screening only, not an investment or drilling model.')
        for table in ('bronze_wells', 'silver_wells', 'rejected_wells'):
            count = connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            print(f'{table}: {count} rows')
        print(f'\nGold question: temperature >= {args.min_temperature:g} C AND flow >= {args.min_flow:g} kg/s')
        rows = screen(connection, args.min_temperature, args.min_flow)
        for well_id, site, temperature, flow, source_row in rows:
            print(f'{well_id}: {site}, {temperature:g} C, {flow:g} kg/s [CSV line {source_row}]')
        if not rows:
            print('No wells match these criteria.')
        print('\nRejected records:')
        for source_row, well_id, reason in connection.execute('SELECT * FROM rejected_wells ORDER BY source_row'):
            print(f'{well_id}: {reason} [CSV line {source_row}]')


if __name__ == '__main__':
    main()
