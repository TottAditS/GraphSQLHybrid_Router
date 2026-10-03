"""Langkah 3 - Sinkronkan struktur jaringan ke Neo4j (graph, lokal lewat Neo4j Desktop).

Neo4j hanya menyimpan apa yang paling cocok untuk graph: hubungan.
  (:User {user_id, gender, age, region})-[:FRIEND]->(:User)     directed, sesuai data asli
  (:User)-[:HAS_HOBBY]->(:Hobby {name})

Atribut ringan (gender, age, region) sengaja diduplikasi di node User supaya
query graph yang butuh filter atribut tidak perlu bolak-balik ke SQLite.
Profil lengkap (pendidikan, kebiasaan, dst.) tetap hanya ada di SQLite.

Script ini membaca CSV langsung (bukan dari SQLite) sehingga tidak bergantung
pada urutan script sebelumnya, dan aman dijalankan ulang (MERGE = idempoten).
PRASYARAT: Neo4j Desktop sudah di-Start dan .env sudah diisi.
"""
from __future__ import annotations

import argparse
import time

import pandas as pd
from neo4j import Driver

from common import (
    banner,
    build_hobby_rows,
    connect_neo4j,
    fail,
    friendly_neo4j_errors,
    read_edges_csv,
    read_users_csv,
)

CONSTRAINTS = {
    "user_id_unique": "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
    "hobby_name_unique": "CREATE CONSTRAINT hobby_name_unique IF NOT EXISTS FOR (h:Hobby) REQUIRE h.name IS UNIQUE",
}

# Semua query memakai UNWIND $rows: satu round-trip membawa ribuan baris sekaligus.
CYPHER_USERS = """
UNWIND $rows AS row
MERGE (u:User {user_id: row.user_id})
SET u.gender = row.gender, u.age = row.age, u.region = row.region
"""
CYPHER_HOBBIES = """
UNWIND $rows AS row
MERGE (:Hobby {name: row.hobby})
"""
CYPHER_HAS_HOBBY = """
UNWIND $rows AS row
MATCH (u:User {user_id: row.user_id})
MATCH (h:Hobby {name: row.hobby})
MERGE (u)-[:HAS_HOBBY]->(h)
"""
CYPHER_FRIEND = """
UNWIND $rows AS row
MATCH (a:User {user_id: row.user_id_1})
MATCH (b:User {user_id: row.user_id_2})
MERGE (a)-[:FRIEND]->(b)
"""


def to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of dict bertipe Python murni (NA/NaN -> None).

    Database: tidak ada. Driver Neo4j tidak bisa mengirim tipe numpy/pandas
    (numpy.int64, pd.NA, NaN), jadi harus dikonversi dulu.
    """
    return df.astype(object).where(df.notna(), None).to_dict("records")


def reset_graph(driver: Driver) -> None:
    """Hapus node User dan Hobby (beserta relasinya) dari sampling sebelumnya.

    Database: Neo4j. Hanya dua label milik proyek ini yang dihapus, jadi data
    lain di DBMS yang sama aman. Dihapus per 10.000 node agar transaksi kecil.
    """
    banner("Reset: menghapus node User dan Hobby lama")
    with driver.session() as session:
        for label in ("User", "Hobby"):
            total = 0
            while True:
                query = f"MATCH (n:{label}) WITH n LIMIT 10000 DETACH DELETE n RETURN count(*) AS deleted"
                deleted = session.execute_write(lambda tx, q=query: tx.run(q).single()["deleted"])
                total += deleted
                if deleted == 0:
                    break
            print(f"  :{label} dihapus: {total:,}")


def create_constraints(driver: Driver) -> None:
    """Buat constraint unique User.user_id dan Hobby.name.

    Database: Neo4j. Dilakukan SEBELUM insert: constraint otomatis membuat index,
    sehingga MERGE/MATCH by user_id cepat (tanpa index, tiap MERGE memindai semua
    node), dan mencegah node ganda.
    """
    banner("Membuat constraint")
    with driver.session() as session:
        for name, statement in CONSTRAINTS.items():
            session.run(statement).consume()
            print(f"  {name}: siap")
        session.run("CALL db.awaitIndexes(300)").consume()  # tunggu index pendukung berstatus ONLINE


def load_in_batches(driver: Driver, label: str, query: str, records: list[dict], batch_size: int) -> dict:
    """Kirim records ke Neo4j per batch lewat UNWIND + MERGE, cetak progres tiap batch.

    Database: Neo4j. Per-batch (bukan per-baris) karena tiap round-trip ke
    server mahal; satu transaksi untuk 1.000 baris jauh lebih cepat daripada
    1.000 transaksi. execute_write otomatis mengulang kalau ada error sementara.
    """
    totals = {"nodes": 0, "relationships": 0}
    n_batches = max(1, -(-len(records) // batch_size))
    started = time.perf_counter()
    with driver.session() as session:
        for i in range(n_batches):
            batch = records[i * batch_size:(i + 1) * batch_size]
            counters = session.execute_write(lambda tx, b=batch: tx.run(query, rows=b).consume().counters)
            totals["nodes"] += counters.nodes_created
            totals["relationships"] += counters.relationships_created
            done = min((i + 1) * batch_size, len(records))
            print(f"  [{label}] batch {i + 1}/{n_batches}  ({done:,}/{len(records):,} baris)  "
                  f"+{counters.nodes_created} node, +{counters.relationships_created} relasi", flush=True)
    print(f"  [{label}] selesai dalam {time.perf_counter() - started:.1f} dtk")
    return totals


def count(driver: Driver, query: str) -> int:
    with driver.session() as session:
        return session.execute_read(lambda tx: tx.run(query).single()[0])


def summarize(driver: Driver, expected: dict[str, int]) -> None:
    """Hitung ulang isi graph di Neo4j dan bandingkan dengan isi CSV.

    Database: Neo4j (count store, jadi cepat). Selisih berarti ada sisa data dari
    sampling sebelumnya (jalankan dengan --reset) atau ada edge yang ujungnya tak dikenal.
    """
    banner("Ringkasan akhir (isi graph sekarang vs isi CSV)")
    actual = {
        "node User": count(driver, "MATCH (u:User) RETURN count(u)"),
        "node Hobby": count(driver, "MATCH (h:Hobby) RETURN count(h)"),
        "relasi FRIEND": count(driver, "MATCH (:User)-[r:FRIEND]->(:User) RETURN count(r)"),
        "relasi HAS_HOBBY": count(driver, "MATCH (:User)-[r:HAS_HOBBY]->(:Hobby) RETURN count(r)"),
    }
    all_ok = True
    for name, value in actual.items():
        ok = value == expected[name]
        all_ok &= ok
        print(f"  {name:<17}: {value:>8,}   (CSV: {expected[name]:,})  {'OK' if ok else 'TIDAK COCOK'}")
    print(f"  total node        : {actual['node User'] + actual['node Hobby']:,}")
    print(f"  total relasi      : {actual['relasi FRIEND'] + actual['relasi HAS_HOBBY']:,}")
    if not all_ok:
        print("\n  PERINGATAN: jumlah tidak cocok. Kemungkinan graph masih berisi sisa sampling lama -> "
              "jalankan ulang dengan: python scripts/03_sync_to_neo4j.py --reset")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinkronkan users + edges (CSV) ke Neo4j lokal.")
    parser.add_argument("--batch-size", type=int, default=1000, help="jumlah baris per transaksi (default 1000)")
    parser.add_argument("--reset", action="store_true",
                        help="hapus dulu node User/Hobby lama (pakai kalau Anda mengganti hasil sampling)")
    args = parser.parse_args()
    if args.batch_size < 1:
        fail("--batch-size harus >= 1")

    users = read_users_csv()
    edges = read_edges_csv()
    hobby_rows = build_hobby_rows(users)
    print(f"CSV dibaca: {len(users):,} user, {len(edges):,} edge, {len(hobby_rows):,} pasangan user-hobi")

    expected = {
        "node User": len(users),
        "node Hobby": hobby_rows["hobby"].nunique(),
        "relasi FRIEND": len(edges),
        "relasi HAS_HOBBY": len(hobby_rows),
    }
    user_records = to_records(users[["user_id", "gender", "age", "region"]])
    hobby_records = to_records(hobby_rows[["hobby"]].drop_duplicates())
    has_hobby_records = to_records(hobby_rows)
    friend_records = to_records(edges)

    driver = connect_neo4j()
    started = time.perf_counter()
    try:
        with friendly_neo4j_errors():
            print(f"Terhubung ke Neo4j. Batch size: {args.batch_size}")
            if args.reset:
                reset_graph(driver)
            create_constraints(driver)

            banner("Mengisi graph")
            load_in_batches(driver, "User", CYPHER_USERS, user_records, args.batch_size)
            load_in_batches(driver, "Hobby", CYPHER_HOBBIES, hobby_records, args.batch_size)
            load_in_batches(driver, "HAS_HOBBY", CYPHER_HAS_HOBBY, has_hobby_records, args.batch_size)
            load_in_batches(driver, "FRIEND", CYPHER_FRIEND, friend_records, args.batch_size)

            summarize(driver, expected)
    finally:
        driver.close()
    print(f"\nSelesai dalam {time.perf_counter() - started:.1f} dtk.")
    print("Coba di Neo4j Browser:  MATCH (u:User)-[f:FRIEND]->(v:User) RETURN u, f, v LIMIT 50")


if __name__ == "__main__":
    main()
