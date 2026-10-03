"""Langkah 2 - Muat data profil ke SQLite (data/pokec.db).

Pembagian tugas di proyek ini: SQLite menyimpan ATRIBUT (siapa user ini: umur,
pendidikan, kebiasaan, hobi), sedangkan hubungan pertemanan hanya hidup di
Neo4j. Karena itu script ini HANYA memakai users_sample.csv - edges tidak
dimasukkan ke SQLite (satu-satunya pengecualian: tabel `friendships` untuk
benchmark, yang dibuat oleh fungsi bandingkan_performa_query di script 04).

Tabel:
  users   : 1 baris per user, 18 kolom atribut, PRIMARY KEY user_id.
  hobbies : many-to-many user <-> hobi, hasil memecah kolom `hobbies` (string
            gabungan "a, b, c") jadi satu baris per pasangan.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from common import (
    SQLITE_PATH,
    banner,
    build_hobby_rows,
    fail,
    read_users_csv,
)

DDL = """
CREATE TABLE users (
    user_id                       INTEGER PRIMARY KEY,   -- PK = otomatis ter-index
    public                        INTEGER CHECK (public IN (0, 1)),   -- 1 = semua pertemanan publik
    completion_percentage         INTEGER,
    gender                        INTEGER CHECK (gender IN (0, 1)),   -- 1 = pria, 0 = wanita
    region                        TEXT NOT NULL,
    last_login                    TEXT,                  -- 'YYYY-MM-DD HH:MM:SS'
    registration                  TEXT,
    age                           INTEGER,               -- NULL kalau tidak diisi / tidak valid
    body_type                     TEXT,
    eye_color                     TEXT,
    hair_color                    TEXT,
    hair_type                     TEXT,
    completed_level_of_education  TEXT,
    favourite_color               TEXT,
    relation_to_smoking           TEXT,
    relation_to_alcohol           TEXT,
    sign_in_zodiac                TEXT,
    marital_status                TEXT
);

CREATE TABLE hobbies (
    user_id  INTEGER NOT NULL REFERENCES users(user_id),
    hobby    TEXT    NOT NULL,
    PRIMARY KEY (user_id, hobby)          -- index untuk pencarian per user_id
) WITHOUT ROWID;

CREATE INDEX idx_hobbies_hobby ON hobbies(hobby);   -- pencarian sebaliknya: hobi -> user
"""
USER_COLUMNS = [
    "user_id", "public", "completion_percentage", "gender", "region", "last_login", "registration",
    "age", "body_type", "eye_color", "hair_color", "hair_type", "completed_level_of_education",
    "favourite_color", "relation_to_smoking", "relation_to_alcohol", "sign_in_zodiac", "marital_status",
]


def create_database() -> sqlite3.Connection:
    """Buat pokec.db baru (file lama dihapus) lengkap dengan skema users + hobbies.

    Database: SQLite. Dibuat ulang dari nol supaya menjalankan script ini
    berkali-kali selalu menghasilkan isi yang sama.
    """
    try:
        SQLITE_PATH.unlink(missing_ok=True)
    except PermissionError:
        fail(f"{SQLITE_PATH.name} sedang dibuka program lain (mis. DB Browser). Tutup dulu lalu coba lagi.")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    return conn


def load_tables(conn: sqlite3.Connection, users: pd.DataFrame, hobby_rows: pd.DataFrame) -> None:
    """Masukkan data CSV ke tabel users dan hobbies.

    Database: SQLite. users dulu, baru hobbies, karena hobbies punya foreign
    key ke users. Pakai pandas.to_sql (executemany di balik layar).
    """
    users[USER_COLUMNS].to_sql("users", conn, if_exists="append", index=False, chunksize=1000)
    hobby_rows.to_sql("hobbies", conn, if_exists="append", index=False, chunksize=1000)
    conn.commit()


def validate(conn: sqlite3.Connection, users: pd.DataFrame, hobby_rows: pd.DataFrame) -> None:
    """Cek jumlah baris, contoh data, integritas, dan pemakaian index.

    Database: SQLite.
    """
    banner("Validasi jumlah baris")
    n_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    n_hobbies = conn.execute("SELECT COUNT(*) FROM hobbies").fetchone()[0]
    n_distinct = conn.execute("SELECT COUNT(DISTINCT hobby) FROM hobbies").fetchone()[0]
    n_with_hobby = conn.execute("SELECT COUNT(DISTINCT user_id) FROM hobbies").fetchone()[0]
    print(f"  users   : {n_users:,} baris  (CSV: {len(users):,})  {'OK' if n_users == len(users) else 'TIDAK COCOK!'}")
    print(f"  hobbies : {n_hobbies:,} baris (hasil pecahan: {len(hobby_rows):,})  "
          f"{'OK' if n_hobbies == len(hobby_rows) else 'TIDAK COCOK!'}")
    print(f"            {n_with_hobby:,} user punya hobi, {n_distinct} hobi berbeda")
    if n_users != len(users) or n_hobbies != len(hobby_rows):
        fail("Jumlah baris di SQLite tidak sama dengan CSV.")

    banner("Contoh baris tabel users (3 baris pertama, ditampilkan menurun)")
    cursor = conn.execute("SELECT * FROM users ORDER BY user_id LIMIT 3")
    columns, rows = [d[0] for d in cursor.description], cursor.fetchall()
    for i, name in enumerate(columns):  # nilai asli SQLite (NULL tetap NULL, integer tetap integer)
        cells = (("(NULL)" if row[i] is None else str(row[i])).ljust(30) for row in rows)
        print(f"  {name:<30}" + " ".join(cells))

    banner("Contoh baris tabel hobbies")
    first_user = conn.execute("SELECT user_id FROM hobbies ORDER BY user_id LIMIT 1").fetchone()[0]
    print(pd.read_sql_query("SELECT * FROM hobbies WHERE user_id = ?", conn, params=(first_user,)).to_string(index=False))
    print("\n  Hobi terpopuler:")
    top = pd.read_sql_query(
        "SELECT hobby, COUNT(*) AS jumlah_user FROM hobbies GROUP BY hobby ORDER BY jumlah_user DESC LIMIT 5", conn
    )
    print("  " + top.to_string(index=False).replace("\n", "\n  "))

    banner("Integritas dan index")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    print(f"  integrity_check  : {integrity}")
    print(f"  foreign_key_check: {'OK, tidak ada pelanggaran' if not fk_violations else fk_violations[:3]}")
    top_hobby = top.loc[0, "hobby"]
    queries = {
        "cari user per user_id   ": ("SELECT * FROM users WHERE user_id = ?", first_user),
        "hobi milik satu user    ": ("SELECT hobby FROM hobbies WHERE user_id = ?", first_user),
        "user pemilik satu hobi  ": ("SELECT user_id FROM hobbies WHERE hobby = ?", top_hobby),
    }
    for label, (sql, value) in queries.items():
        plan = " | ".join(row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, (value,)))
        print(f"  {label}: {plan}")


def main() -> None:
    users = read_users_csv()
    missing = set(USER_COLUMNS) - set(users.columns)
    if missing:
        fail(f"Kolom {sorted(missing)} tidak ada di users_sample.csv. Jalankan ulang scripts/01_subsample_data.py.")
    hobby_rows = build_hobby_rows(users)

    banner(f"Membuat {SQLITE_PATH.name} dan memuat data")
    conn = create_database()
    try:
        load_tables(conn, users, hobby_rows)
        validate(conn, users, hobby_rows)
    finally:
        conn.close()
    print(f"\nSelesai. Database: {SQLITE_PATH} ({SQLITE_PATH.stat().st_size / 1e6:.1f} MB)")
    print("Catatan: edges (pertemanan) sengaja TIDAK ada di SQLite - itu tugas Neo4j (script 03).")


if __name__ == "__main__":
    main()
