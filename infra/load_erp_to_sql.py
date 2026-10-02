"""Load the generated legacy ERP (data/raw/erp/*.parquet) into Azure SQL (sqldb-nestle-erp).

    pip install pyodbc
    python infra/load_erp_to_sql.py                 # asks for the SQL login password
    python infra/load_erp_to_sql.py --only sales_order_lines --year 2025   # resume one part

Uses pyodbc fast_executemany in 50k-row batches. Recreates the schema first (sql/01_erp_schema.sql)
unless --no-ddl or --only is given. Prints source vs target row counts at the end (first reconciliation).
"""
import argparse
import getpass
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pyodbc

ROOT = Path(__file__).resolve().parents[1]
ERP = ROOT / "data" / "raw" / "erp"
SERVER = os.getenv("NESTLE_SQL_SERVER", "sql-lloyds-joaopaura.database.windows.net")
DATABASE = os.getenv("NESTLE_SQL_DB", "sqldb-nestle-erp")
ORDER = ["countries", "products", "customers", "price_list", "standard_cost", "customer_changes", "product_changes",
         "promotions", "sales_orders", "sales_order_lines", "returns"]
BATCH = 50_000


def connect(user: str, pwd: str) -> pyodbc.Connection:
    drivers = sorted(d for d in pyodbc.drivers() if re.match(r"ODBC Driver \d+ for SQL Server", d))
    if not drivers:
        sys.exit("No 'ODBC Driver xx for SQL Server' found. Install ODBC Driver 18: https://aka.ms/downloadmsodbcsql")
    cs = (f"DRIVER={{{drivers[-1]}}};SERVER=tcp:{SERVER},1433;DATABASE={DATABASE};UID={user};PWD={pwd};"
          "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=120;")
    for attempt in range(4):                       # free-offer databases auto-pause: first connect wakes them up
        try:
            return pyodbc.connect(cs, autocommit=False)
        except pyodbc.Error as e:
            print(f"  connect attempt {attempt + 1} failed ({str(e)[:90]}...), retrying in 30 s")
            time.sleep(30)
    sys.exit("Could not connect. Check firewall (Networking > add your client IP) and the login.")


def run_ddl(cn: pyodbc.Connection) -> None:
    sql = (ROOT / "sql" / "01_erp_schema.sql").read_text(encoding="utf-8")
    cur = cn.cursor()
    for block in re.split(r"^\s*GO\s*$", sql, flags=re.M | re.I):
        if block.strip():
            cur.execute(block)
    cn.commit()
    print("Schema erp recreated")


def files(table: str, year: int | None) -> list[Path]:
    single = ERP / f"{table}.parquet"
    if single.exists():
        return [single]
    parts = sorted((ERP / table).glob("year=*/part-*.parquet"))
    return [p for p in parts if year is None or f"year={year}" in str(p)]


def to_rows(df: pd.DataFrame) -> list[tuple]:
    out = df.astype(object).where(df.notna(), None)
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            out[c] = [None if v is None else v.to_pydatetime() for v in out[c]]
    return list(out.itertuples(index=False, name=None))


def load(cn: pyodbc.Connection, table: str, year: int | None) -> int:
    cur = cn.cursor(); cur.fast_executemany = True
    total = 0
    for f in files(table, year):
        pf = pq.ParquetFile(f)
        cols = pf.schema_arrow.names
        sql = f"INSERT INTO erp.{table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        t0 = time.time()
        for batch in pf.iter_batches(batch_size=BATCH):
            cur.executemany(sql, to_rows(batch.to_pandas()))
            cn.commit()
            total += batch.num_rows
            print(f"\r  {table:<18} {f.parent.name if f.parent != ERP else '':<10} {total:>12,} rows "
                  f"({total / max(time.time() - t0, 1):,.0f} rows/s)", end="", flush=True)
        print()
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=os.getenv("NESTLE_SQL_USER"))
    ap.add_argument("--only"); ap.add_argument("--year", type=int); ap.add_argument("--no-ddl", action="store_true")
    a = ap.parse_args()
    user = a.user or input("SQL login (admin user of sql-lloyds-joaopaura): ")
    pwd = os.getenv("NESTLE_SQL_PASSWORD") or getpass.getpass("Password: ")
    cn = connect(user, pwd)
    print(f"Connected to {SERVER}/{DATABASE}")
    if not (a.no_ddl or a.only):
        run_ddl(cn)
    t0 = time.time()
    for t in ([a.only] if a.only else ORDER):
        load(cn, t, a.year)
    print(f"Load finished in {(time.time() - t0) / 60:,.1f} min\n\nSource (manifest) vs target (Azure SQL):")
    manifest = json.loads((ROOT / "data" / "raw" / "manifest.json").read_text())
    cur = cn.cursor(); ok = True
    for t in ORDER:
        n = cur.execute(f"SELECT COUNT_BIG(*) FROM erp.{t}").fetchone()[0]
        flag = "OK " if n == manifest.get(t) else "DIFF"; ok &= flag == "OK "
        print(f"  {flag} {t:<18} source {manifest.get(t, 0):>12,}  target {n:>12,}")
    print("All tables match." if ok else "Some tables differ: rerun with --only <table> after truncating it.")


if __name__ == "__main__":
    main()
