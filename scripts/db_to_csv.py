import argparse
import csv
import sqlite3
import sys
from pathlib import Path


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [row[0] for row in rows]


def export_table(conn: sqlite3.Connection, table: str, out_path: Path, batch_size: int) -> int:
    cursor = conn.execute(f'SELECT * FROM "{table}"')
    columns = [description[0] for description in cursor.description]

    total = 0
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            writer.writerows(rows)
            total += len(rows)
            print(f"  {table}: {total:,} rows written", end="\r")
    print(f"  {table}: {total:,} rows written -> {out_path}")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path, help="Path to the SQLite .db file")
    parser.add_argument("--out-dir", type=Path, default=Path("csv_export"), help="Directory to write CSVs into")
    parser.add_argument("--table", help="Export only this table (default: all tables)")
    parser.add_argument("--batch-size", type=int, default=50_000, help="Rows fetched per batch")
    args = parser.parse_args()

    if not args.db_path.exists():
        sys.exit(f"No such file: {args.db_path}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db_path)
    try:
        tables = [args.table] if args.table else list_tables(conn)
        if not tables:
            sys.exit("No tables found in database.")
        print(f"Exporting {len(tables)} table(s) from {args.db_path} to {args.out_dir}/")
        for table in tables:
            export_table(conn, table, args.out_dir / f"{table}.csv", args.batch_size)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
