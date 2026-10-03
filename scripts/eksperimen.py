"""Eksperimen perbandingan graf vs relasional dan uji kombinasi hybrid, khusus untuk notebooks/1_tes_semua.ipynb.

Isinya (semua fungsi menerima koneksi yang sudah dibuka notebook, tidak membuka koneksi sendiri):
  * Pengukuran: ukur_bergantian() menjalankan beberapa cara menjawab pertanyaan yang SAMA secara bergantian setelah
    pemanasan, supaya JIT/cache/gangguan sistem tidak menguntungkan satu pihak (lihat Georges dkk., 2007).
  * Generator SQL: sql_join_k() dan sql_distinct_k() membuat query k relasi; aturan Cypher "satu relasi tidak dipakai dua
    kali dalam satu path" (Francis dkk., 2018) ditiru di SQL supaya hasil kedua mesin identik.
  * Keluarga query: pencarian titik, agregasi, k relasi, rekomendasi teman, jalur terpendek, dan tiga strategi hybrid
    untuk "teman dari teman dengan filter atribut". Tiap fungsi memeriksa hasilnya sama persis sebelum waktunya dilaporkan.
  * Konsistensi lintas basis data: pemeriksaan atribut/edge/hobi yang diduplikasi, suntik-deteksi-perbaiki "drift".
  * Biaya: lintas batas SQLite-Neo4j, ukuran penyimpanan, overhead per panggilan, skala pada graf sintetis.

Hanya dipakai oleh notebook; script 01-04 tidak bergantung padanya.
"""
from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import statistics
import time
from collections import Counter, deque
from pathlib import Path

import numpy as np
import pandas as pd

from common import PROJECT_ROOT, SQLITE_PATH, read_edges_csv, read_query

HASIL_DIR = PROJECT_ROOT / "docs" / "hasil" / os.environ.get("HASIL_SUBDIR", "")   # HASIL_SUBDIR: simpan per-run (lihat scripts/rangkum_run.py)
BATAS_JOIN = 3_000_000   # SQL JOIN berulang tidak dijalankan kalau path-nya lebih banyak dari ini (terlalu lama; dicatat "dilewati")


# --------------------------------------------------------------------------
# Pengukuran
# --------------------------------------------------------------------------
class SesiCypher:
    """Satu sesi Neo4j yang dipakai berulang; mencatat juga waktu eksekusi di sisi server (ms) tiap panggilan."""

    def __init__(self, driver) -> None:
        self._sesi = driver.session()
        self.total_server_ms = 0.0

    def jalankan(self, query: str, **parameter) -> list[dict]:
        hasil = self._sesi.run(query, **parameter)
        baris = [r.data() for r in hasil]
        ringkasan = hasil.consume()
        self.total_server_ms += (ringkasan.result_available_after or 0) + (ringkasan.result_consumed_after or 0)
        return baris

    def tutup(self) -> None:
        self._sesi.close()


def ringkas(daftar: list[float]) -> dict:
    """Median, kuartil 1 dan 3, serta minimum dan maksimum dari daftar waktu."""
    a = np.asarray(daftar, dtype=float)
    return {"median": float(np.median(a)), "q1": float(np.percentile(a, 25)), "q3": float(np.percentile(a, 75)),
            "min": float(a.min()), "maks": float(a.max())}


def ukur_bergantian(fungsi: dict, ulangi: int = 5, pemanasan: int = 2, bagi: int = 1,
                    sesi: SesiCypher | None = None, nama_neo: str = "neo4j") -> tuple[dict, dict, list[float]]:
    """Jalankan semua `fungsi` (nama -> callable) bergantian: `pemanasan` putaran tidak diukur, lalu `ulangi` putaran diukur.

    Mengembalikan (waktu_ms per nama, hasil terakhir per nama, waktu server Neo4j per putaran). `bagi` membagi waktu
    (untuk fungsi yang mengulang pekerjaan kecil berkali-kali). Waktu server hanya dicatat kalau `sesi` diberikan.
    """
    hasil: dict = {}
    for _ in range(pemanasan):
        for nama, f in fungsi.items():
            hasil[nama] = f()
    waktu = {nama: [] for nama in fungsi}
    server: list[float] = []
    for _ in range(ulangi):
        for nama, f in fungsi.items():
            awal_server = sesi.total_server_ms if sesi else 0.0
            mulai = time.perf_counter()
            hasil[nama] = f()
            waktu[nama].append((time.perf_counter() - mulai) * 1000 / bagi)
            if sesi and nama == nama_neo:
                server.append((sesi.total_server_ms - awal_server) / bagi)
    return waktu, hasil, server


def token_query(nama_file: str | None = None, teks: str | None = None) -> int:
    """Jumlah token (dipisah spasi) sebuah query tanpa baris komentar: ukuran kasar 'seberapa panjang menulisnya'."""
    isi = teks if teks is not None else read_query(nama_file)
    tanpa_komentar = [b for b in isi.splitlines() if not b.strip().startswith(("--", "//"))]
    return len(" ".join(tanpa_komentar).split())


def simpan_hasil(nama: str, objek) -> str:
    """Simpan DataFrame (CSV) atau dict (JSON) ke docs/hasil/ supaya angka laporan bisa ditelusuri."""
    HASIL_DIR.mkdir(parents=True, exist_ok=True)
    if isinstance(objek, pd.DataFrame):
        objek.to_csv(HASIL_DIR / f"{nama}.csv", index=False)
        return str((HASIL_DIR / f"{nama}.csv").relative_to(PROJECT_ROOT)).replace(os.sep, "/")
    (HASIL_DIR / f"{nama}.json").write_text(json.dumps(objek, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return str((HASIL_DIR / f"{nama}.json").relative_to(PROJECT_ROOT)).replace(os.sep, "/")


# --------------------------------------------------------------------------
# Tabel friendships (salinan edge di SQLite, khusus benchmark) dan generator SQL
# --------------------------------------------------------------------------
def bangun_friendships(conn, edges=None, tabel: str = "friendships") -> int:
    """Buat tabel edge di SQLite dengan PRIMARY KEY (user_id_1, user_id_2) WITHOUT ROWID; kembalikan jumlah barisnya.

    Database: SQLite. `edges` = DataFrame/daftar pasangan (default: edges_sample.csv). Tabel dibuat ulang tiap kali.
    """
    pasangan = (read_edges_csv().to_numpy().tolist() if edges is None
                else (edges.to_numpy().tolist() if isinstance(edges, pd.DataFrame) else [list(e) for e in edges]))
    conn.executescript(f"""
        DROP TABLE IF EXISTS {tabel};
        CREATE TABLE {tabel} (user_id_1 INTEGER NOT NULL, user_id_2 INTEGER NOT NULL,
                              PRIMARY KEY (user_id_1, user_id_2)) WITHOUT ROWID;""")
    conn.executemany(f"INSERT INTO {tabel} VALUES (?, ?)", pasangan)
    conn.commit()
    conn.execute(f"ANALYZE {tabel}")
    return len(pasangan)


def sql_join_k(k: int, tabel: str = "friendships") -> str:
    """SQL 'tepat k relasi' dengan k-1 JOIN. Pasangan relasi yang berjarak >= 2 dalam path dilarang sama (aturan Cypher)."""
    gabung = [f"FROM {tabel} AS f1"] + [
        f"JOIN {tabel} AS f{i} ON f{i}.user_id_1 = f{i - 1}.user_id_2" for i in range(2, k + 1)]
    syarat = ["f1.user_id_1 = :user_id", f"f{k}.user_id_2 <> :user_id"]
    syarat += [f"NOT (f{j}.user_id_1 = f{i}.user_id_1 AND f{j}.user_id_2 = f{i}.user_id_2)"
               for j in range(3, k + 1) for i in range(1, j - 1)]
    return (f"SELECT COUNT(DISTINCT f{k}.user_id_2) AS total,\n       COALESCE(SUM(DISTINCT f{k}.user_id_2), 0) AS checksum,\n"
            "       COUNT(*) AS jumlah_path\n" + "\n".join(gabung) + "\nWHERE " + "\n  AND ".join(syarat))


def sql_distinct_k(k: int, tabel: str = "friendships") -> str:
    """SQL 'dapat dicapai lewat k langkah' dengan DISTINCT di tiap level (jumlah baris antara tidak meledak)."""
    bagian = [f"l1 AS (SELECT DISTINCT user_id_2 AS id FROM {tabel} WHERE user_id_1 = :user_id)"] + [
        f"l{i} AS (SELECT DISTINCT f.user_id_2 AS id FROM {tabel} AS f JOIN l{i - 1} ON f.user_id_1 = l{i - 1}.id)"
        for i in range(2, k + 1)]
    return ("WITH " + ",\n     ".join(bagian) + f"\nSELECT COUNT(*) AS total, COALESCE(SUM(id), 0) AS checksum\n"
            f"FROM l{k}\nWHERE id <> :user_id")


def cypher_k(k: int, label: str = "User", relasi: str = "FRIEND") -> str:
    """Cypher 'tepat k relasi' dari queries/teman_k_level.cypher (label/relasi bisa diganti untuk graf sintetis)."""
    teks = read_query("teman_k_level.cypher").replace("__K__", str(k))
    return teks.replace(":User", f":{label}").replace(":FRIEND", f":{relasi}")


def cypher_k_unik(k: int, label: str = "User", relasi: str = "FRIEND") -> str:
    """Cypher 'tepat k relasi' yang HANYA meminta himpunan user unik (queries/teman_k_level_unik.cypher)."""
    teks = read_query("teman_k_level_unik.cypher").replace("__K__", str(k))
    return teks.replace(":User", f":{label}").replace(":FRIEND", f":{relasi}")


def operator_rencana(sesi: SesiCypher, query: str, **parameter) -> list[str]:
    """Nama operator pada rencana EXPLAIN sebuah query Cypher (query tidak dijalankan), mis. 'VarLengthExpand(Pruning)'."""
    ringkasan = sesi._sesi.run("EXPLAIN " + query, **parameter).consume()
    nama: list[str] = []

    def telusuri(simpul: dict) -> None:
        nama.append(simpul["operatorType"])
        for anak in simpul.get("children", []):
            telusuri(anak)

    telusuri(ringkasan.plan)
    return nama


# --------------------------------------------------------------------------
# Jawaban kunci tambahan (Python murni)
# --------------------------------------------------------------------------
class _Kebanyakan(Exception):
    pass


def k_hop_python(keluar: dict, a: int, k: int, batas_path: int = 500_000) -> tuple[int, int, int] | None:
    """(jumlah_path, jumlah_unik, checksum) untuk tepat k relasi tanpa relasi berulang; None kalau path > batas_path."""
    unik: set[int] = set()
    dipakai: list[tuple[int, int]] = []
    jumlah = 0

    def dfs(sekarang: int, kedalaman: int) -> None:
        nonlocal jumlah
        for berikut in keluar.get(sekarang, ()):
            relasi = (sekarang, berikut)
            if relasi in dipakai:
                continue
            if kedalaman + 1 == k:
                if berikut != a:
                    jumlah += 1
                    unik.add(berikut)
                    if jumlah > batas_path:
                        raise _Kebanyakan
            else:
                dipakai.append(relasi)
                dfs(berikut, kedalaman + 1)
                dipakai.pop()

    try:
        dfs(a, 0)
    except _Kebanyakan:
        return None
    return jumlah, len(unik), sum(unik)


def jarak_python(keluar: dict, a: int, b: int, maks: int = 8) -> int | None:
    """Panjang jalur terpendek berarah a -> b dengan pencarian melebar (BFS); None kalau > maks atau tidak terhubung."""
    terlihat, antrian = {a}, deque([(a, 0)])
    while antrian:
        x, d = antrian.popleft()
        if d == maks:
            continue
        for y in keluar.get(x, ()):
            if y == b:
                return d + 1
            if y not in terlihat:
                terlihat.add(y)
                antrian.append((y, d + 1))
    return None


def pilih_user_uji(derajat: pd.DataFrame, jumlah: int = 5) -> list[tuple[int, int]]:
    """User uji bertingkat menurut out-degree: hub, persentil 1, 10, 25, 50, ... (graf sosial itu timpang)."""
    aktif = derajat[derajat["out_degree"] > 0].sort_values(["out_degree", "user_id"], ascending=[False, True])
    dipilih: dict[int, int] = {}
    for p in [0.0, 0.01, 0.10, 0.25, 0.50, 0.75, 0.90][:jumlah]:
        baris = aktif.iloc[min(int(len(aktif) * p), len(aktif) - 1)]
        dipilih.setdefault(int(baris["user_id"]), int(baris["out_degree"]))
    return list(dipilih.items())


def pemanasan_neo4j(sesi: SesiCypher, users: list[tuple[int, int]], detik: float = 3.0, k: int = 3,
                    cypher: str | None = None) -> int:
    """Jalankan Cypher k relasi keliling user uji selama `detik` detik (JVM yang baru menyala itu dingin). Kembalikan jumlah putaran."""
    query = cypher or cypher_k(k)
    akhir, putaran = time.perf_counter() + detik, 0
    while time.perf_counter() < akhir:
        sesi.jalankan(query, user_id=users[putaran % len(users)][0])
        putaran += 1
    return putaran


def kurva_pemanasan(sesi: SesiCypher, user_id: int, jumlah: int = 30, k: int = 3) -> list[float]:
    """Waktu (ms) panggilan ke-1, ke-2, ... query yang SAMA; di server yang baru menyala tampak mulai lambat lalu menurun."""
    query, hasil = cypher_k(k), []
    for _ in range(jumlah):
        mulai = time.perf_counter()
        sesi.jalankan(query, user_id=user_id)
        hasil.append((time.perf_counter() - mulai) * 1000)
    return hasil


# --------------------------------------------------------------------------
# Keluarga query: dua mesin, pertanyaan yang sama, hasil harus identik
# --------------------------------------------------------------------------
def overhead_panggilan(sesi: SesiCypher, conn, ulangi: int = 300) -> dict:
    """Biaya tetap satu panggilan: SELECT 1 di SQLite (dalam proses) vs RETURN 1 di Neo4j (lewat Bolt ke server)."""
    waktu, _, server = ukur_bergantian({
        "sqlite": lambda: conn.execute("SELECT 1").fetchone(),
        "neo4j": lambda: sesi.jalankan("RETURN 1 AS x")}, ulangi=ulangi, pemanasan=20, sesi=sesi)
    return {"sqlite_ms": statistics.median(waktu["sqlite"]), "neo4j_ms": statistics.median(waktu["neo4j"]),
            "neo4j_server_ms": statistics.median(server)}


def keluarga_pencarian_titik(sesi: SesiCypher, conn, ids: list[int], ulangi: int = 5) -> dict:
    """Cari profil per user_id untuk banyak id acak. Waktu = per pencarian. Hasil kedua mesin harus sama."""
    sql, cy = read_query("pencarian_titik.sql"), read_query("pencarian_titik.cypher")
    waktu, hasil, server = ukur_bergantian({
        "sqlite": lambda: [tuple(conn.execute(sql, {"user_id": u}).fetchone()) for u in ids],
        "neo4j": lambda: [tuple(sesi.jalankan(cy, user_id=u)[0].values()) for u in ids]},
        ulangi=ulangi, pemanasan=1, bagi=len(ids), sesi=sesi)
    return _baris("Pencarian titik (user_id)", f"{len(ids)} id acak; waktu per pencarian", waktu, server,
                  hasil["sqlite"] == hasil["neo4j"], "pencarian_titik")


def keluarga_agregasi_atribut(sesi: SesiCypher, conn, ulangi: int = 7) -> dict:
    """Jumlah user dan umur rata-rata per gender (seluruh tabel/graf dipindai)."""
    sql, cy = read_query("agregasi_gender.sql"), read_query("agregasi_gender.cypher")
    def norm(baris):   # NULL diurutkan di ujung berbeda oleh SQLite dan Neo4j, jadi urutkan ulang secara seragam
        return sorted(((g, int(n), None if u is None else round(float(u), 4)) for g, n, u in baris),
                      key=lambda t: (t[0] is None, -1 if t[0] is None else t[0]))

    waktu, hasil, server = ukur_bergantian({
        "sqlite": lambda: norm(conn.execute(sql).fetchall()),
        "neo4j": lambda: norm([(r["gender"], r["jumlah"], r["umur_rata2"]) for r in sesi.jalankan(cy)])},
        ulangi=ulangi, pemanasan=2, sesi=sesi)
    return _baris("Agregasi atribut (GROUP BY gender)", "jumlah dan umur rata-rata per gender", waktu, server,
                  hasil["sqlite"] == hasil["neo4j"], "agregasi_gender")


def keluarga_agregasi_derajat(sesi: SesiCypher, conn, ulangi: int = 7) -> dict:
    """10 user dengan out-degree terbesar (agregasi atas seluruh edge)."""
    sql, cy = read_query("agregasi_derajat.sql"), read_query("agregasi_derajat.cypher")
    waktu, hasil, server = ukur_bergantian({
        "sqlite": lambda: [tuple(r) for r in conn.execute(sql).fetchall()],
        "neo4j": lambda: [(r["user_id"], r["out_degree"]) for r in sesi.jalankan(cy)]},
        ulangi=ulangi, pemanasan=2, sesi=sesi)
    return _baris("Agregasi struktur (top-10 out-degree)", "GROUP BY atas semua edge", waktu, server,
                  hasil["sqlite"] == hasil["neo4j"], "agregasi_derajat")


def keluarga_rekomendasi(sesi: SesiCypher, conn, users: list[tuple[int, int]], ulangi: int = 5, limit: int = 10) -> pd.DataFrame:
    """Rekomendasi teman (teman dari teman dengan teman bersama terbanyak), SQL vs Cypher, per user uji."""
    sql, cy = read_query("rekomendasi_teman.sql"), read_query("rekomendasi_teman_inti.cypher")
    baris = []
    for uid, deg in users:
        waktu, hasil, server = ukur_bergantian({
            "sqlite": lambda uid=uid: [tuple(r) for r in conn.execute(sql, {"user_id": uid, "limit": limit}).fetchall()],
            "neo4j": lambda uid=uid: [(r["user_id"], r["teman_bersama"])
                                      for r in sesi.jalankan(cy, user_id=uid, limit=limit)]},
            ulangi=ulangi, pemanasan=2, sesi=sesi)
        baris.append({"user_id": uid, "out_degree": deg, "kandidat": len(hasil["neo4j"]),
                      "sqlite_ms": statistics.median(waktu["sqlite"]), "neo4j_ms": statistics.median(waktu["neo4j"]),
                      "neo4j_server_ms": statistics.median(server), "sama": hasil["sqlite"] == hasil["neo4j"]})
    return pd.DataFrame(baris)


def jumlah_walk(keluar: dict, a: int, k: int) -> int:
    """Banyaknya walk (boleh mengulang relasi) sepanjang k dari a, lewat pemrograman dinamis O(k x edge).

    Hanya perkiraan jumlah path untuk memutuskan apakah enumerasi layak dijalankan: path Cypher (tanpa relasi ganda)
    sedikit lebih sedikit daripada walk.
    """
    cara = {a: 1}
    for _ in range(k):
        berikut: dict[int, int] = {}
        for x, c in cara.items():
            for y in keluar.get(x, ()):
                berikut[y] = berikut.get(y, 0) + c
        cara = berikut
    return sum(cara.values())


def tiga_cara_k_hop(sesi: SesiCypher, conn, user_id: int, k: int, ulangi: int = 5, tabel: str = "friendships",
                    label: str = "User", relasi: str = "FRIEND", acuan_python: tuple | None = None,
                    perkiraan_path: int | None = None) -> dict:
    """Satu user, tepat k relasi, empat cara yang membentuk DUA pasangan setara:

      * menyusuri semua path : SQLite JOIN berulang  <->  Cypher dengan count(p)  (kerjanya sama: enumerasi path)
      * himpunan user unik   : SQLite DISTINCT per level  <->  Cypher tanpa count(p)  (Neo4j boleh memangkas/pruning)

    Keempatnya harus memberi himpunan akhir yang sama (jumlah unik + checksum), dan JOIN harus sama dengan Cypher
    sampai jumlah path-nya. Dua cara yang menyusuri path dilewati kalau jumlah path > BATAS_JOIN (kolom
    `enumerasi_dilewati`). `acuan_python` = hasil k_hop_python (jumlah_path, jumlah_unik, checksum) kalau dihitung.
    """
    cy_enum, cy_unik = cypher_k(k, label, relasi), cypher_k_unik(k, label, relasi)
    sql_join, sql_dist = sql_join_k(k, tabel), sql_distinct_k(k, tabel)
    if perkiraan_path is None:       # tanpa perkiraan: jalankan enumerasi sekali (sekaligus pemanasan) untuk tahu jumlah path
        jumlah_path, perkiraan = int(sesi.jalankan(cy_enum, user_id=user_id)[0]["jumlah_path"]), False
    else:
        jumlah_path, perkiraan = int(perkiraan_path), True
    lewati = jumlah_path > BATAS_JOIN
    if perkiraan and not lewati:     # diputuskan jalan: ambil jumlah path yang sebenarnya
        jumlah_path, perkiraan = int(sesi.jalankan(cy_enum, user_id=user_id)[0]["jumlah_path"]), False
    fungsi = {"neo4j_unik": lambda: tuple(sesi.jalankan(cy_unik, user_id=user_id)[0].values()),
              "sqlite_distinct": lambda: tuple(conn.execute(sql_dist, {"user_id": user_id}).fetchone())}
    if not lewati:
        fungsi["neo4j_enum"] = lambda: tuple(sesi.jalankan(cy_enum, user_id=user_id)[0].values())
        fungsi["sqlite_join"] = lambda: tuple(conn.execute(sql_join, {"user_id": user_id}).fetchone())
    waktu, hasil, server = ukur_bergantian(fungsi, ulangi=ulangi, pemanasan=1, sesi=sesi, nama_neo="neo4j_enum" if not lewati else "neo4j_unik")
    unik = hasil["neo4j_unik"]
    med = lambda nama: statistics.median(waktu[nama]) if nama in waktu else float("nan")  # noqa: E731
    baris = {"user_id": user_id, "k": k, "jumlah_path": jumlah_path, "unik": int(unik[0]),
             "sqlite_join_ms": med("sqlite_join"), "neo4j_enum_ms": med("neo4j_enum"),
             "sqlite_distinct_ms": med("sqlite_distinct"), "neo4j_unik_ms": med("neo4j_unik"),
             "neo4j_enum_server_ms": statistics.median(server) if not lewati else float("nan"),
             "enumerasi_dilewati": lewati, "jumlah_path_perkiraan": perkiraan}
    sama_himpunan = hasil["sqlite_distinct"] == unik
    if not lewati:
        sama_himpunan = sama_himpunan and hasil["sqlite_join"] == hasil["neo4j_enum"] and hasil["neo4j_enum"][:2] == unik
    baris["hasil_sama"] = bool(sama_himpunan)
    baris["python_sama"] = None if acuan_python is None else (acuan_python == (jumlah_path, unik[0], unik[1]))
    return baris


def keluarga_k_hop(sesi: SesiCypher, conn, users: list[tuple[int, int]], ks=(1, 2, 3), ulangi: int = 5,
                   keluar: dict | None = None, ulangi_dalam: int = 3) -> pd.DataFrame:
    """Sapuan kedalaman: untuk tiap (user, k) jalankan tiga_cara_k_hop(); k >= 4 hanya untuk user non-hub dan diulang lebih sedikit."""
    baris = []
    for k in ks:
        for indeks, (uid, deg) in enumerate(users):
            if k >= 4 and indeks == 0:
                continue   # hub pada k >= 4 menghasilkan puluhan juta path; polanya sudah terlihat tanpa itu
            perkiraan = jumlah_walk(keluar, uid, k) if keluar is not None else None
            acuan = k_hop_python(keluar, uid, k) if keluar is not None and perkiraan <= 450_000 else None   # Python lambat: hanya yang kecil
            r = tiga_cara_k_hop(sesi, conn, uid, k, ulangi if k < 4 else ulangi_dalam, acuan_python=acuan,
                                perkiraan_path=perkiraan)
            r["out_degree"] = deg
            baris.append(r)
    return pd.DataFrame(baris)


def pilih_pasangan_jalur(keluar: dict, pengguna: list[int], jumlah_terhubung: int = 16, jumlah_tidak: int = 4,
                         seed: int = 7) -> list[tuple[int, int, int | None]]:
    """Pasangan (a, b, jarak_python) acak: sebagian terhubung (jarak 1-8) dan sebagian tidak terhubung dalam 8 relasi."""
    rng = random.Random(seed)
    aktif = [u for u in pengguna if keluar.get(u)]
    terhubung, tidak = [], []
    while len(terhubung) < jumlah_terhubung or len(tidak) < jumlah_tidak:
        a, b = rng.sample(aktif, 2)
        jarak = jarak_python(keluar, a, b)
        if jarak is None and len(tidak) < jumlah_tidak:
            tidak.append((a, b, None))
        elif jarak is not None and len(terhubung) < jumlah_terhubung:
            terhubung.append((a, b, jarak))
    return terhubung + tidak


def keluarga_jalur_terpendek(sesi: SesiCypher, conn, pasangan: list[tuple[int, int, int | None]], ulangi: int = 3) -> pd.DataFrame:
    """Jalur terpendek berarah (maks 8 relasi): Cypher shortestPath vs SQL recursive CTE vs BFS Python (jawaban kunci)."""
    sql, cy = read_query("jalur_terpendek.sql"), read_query("jalur_terpendek.cypher")
    baris = []
    for a, b, jarak in pasangan:
        waktu, hasil, server = ukur_bergantian({
            "sqlite": lambda a=a, b=b: (lambda r: None if r is None else r[0])(conn.execute(sql, {"a": a, "b": b}).fetchone()),
            "neo4j": lambda a=a, b=b: (lambda r: r[0]["panjang"] if r else None)(sesi.jalankan(cy, a=a, b=b))},
            ulangi=ulangi, pemanasan=1, sesi=sesi)
        baris.append({"a": a, "b": b, "jarak_python": jarak, "jarak_sqlite": hasil["sqlite"], "jarak_neo4j": hasil["neo4j"],
                      "sqlite_ms": statistics.median(waktu["sqlite"]), "neo4j_ms": statistics.median(waktu["neo4j"]),
                      "sama": jarak == hasil["sqlite"] == hasil["neo4j"]})
    return pd.DataFrame(baris)


def keluarga_strategi_hybrid(sesi: SesiCypher, conn, users: list[tuple[int, int]], ulangi: int = 5) -> pd.DataFrame:
    """'Teman dari teman, pria 20-30 tahun': S1 semua di SQL, S2 semua di Neo4j (atribut duplikat), S3 hybrid (id dari Neo4j, filter di SQLite)."""
    sql, cy, cy_id = read_query("fof_filter.sql"), read_query("fof_filter.cypher"), read_query("fof_ids.cypher")
    baris = []
    for uid, deg in users:
        dikirim = [0]

        def s3(uid=uid, dikirim=dikirim):
            ids = [r["user_id"] for r in sesi.jalankan(cy_id, user_id=uid)]
            dikirim[0] = len(ids)
            total = jumlah = 0
            for i in range(0, len(ids), 500):
                bagian = ids[i:i + 500]
                for (u,) in conn.execute(f"SELECT user_id FROM users WHERE user_id IN ({','.join('?' * len(bagian))}) "
                                         "AND gender = 1 AND age BETWEEN 20 AND 30", bagian):
                    total += 1
                    jumlah += u
            return total, jumlah

        waktu, hasil, server = ukur_bergantian({
            "s1_sql": lambda uid=uid: tuple(conn.execute(sql, {"user_id": uid}).fetchone()),
            "neo4j": lambda uid=uid: tuple(sesi.jalankan(cy, user_id=uid)[0].values()),
            "s3_hybrid": s3}, ulangi=ulangi, pemanasan=2, sesi=sesi)
        baris.append({"user_id": uid, "out_degree": deg, "lolos_filter": hasil["neo4j"][0], "id_dikirim_ke_sqlite": dikirim[0],
                      "s1_sql_ms": statistics.median(waktu["s1_sql"]), "s2_neo4j_ms": statistics.median(waktu["neo4j"]),
                      "s3_hybrid_ms": statistics.median(waktu["s3_hybrid"]),
                      "sama": hasil["s1_sql"] == hasil["neo4j"] == hasil["s3_hybrid"]})
    return pd.DataFrame(baris)


def _baris(keluarga: str, ket: str, waktu: dict, server: list[float], sama: bool, berkas: str) -> dict:
    sql, neo = statistics.median(waktu["sqlite"]), statistics.median(waktu["neo4j"])
    return {"keluarga": keluarga, "keterangan": ket, "sqlite_ms": sql, "neo4j_ms": neo,
            "neo4j_server_ms": statistics.median(server), "sqlite_q1": ringkas(waktu["sqlite"])["q1"],
            "sqlite_q3": ringkas(waktu["sqlite"])["q3"], "neo4j_q1": ringkas(waktu["neo4j"])["q1"],
            "neo4j_q3": ringkas(waktu["neo4j"])["q3"], "sama": bool(sama), "berkas_query": berkas}


# --------------------------------------------------------------------------
# Konsistensi lintas basis data, deteksi dan perbaikan drift
# --------------------------------------------------------------------------
KOLOM_DUPLIKAT = ("gender", "age", "region")


def selisih_himpunan(sesi: SesiCypher, conn) -> dict:
    """Bandingkan isi Neo4j dengan isi SQLite sebagai HIMPUNAN: user, edge (tabel friendships), pasangan user-hobi.

    Mengembalikan jumlah anggota yang hanya ada di satu sisi. Semua nilainya harus 0 kalau kedua basis data konsisten.
    """
    neo_user = {r["user_id"] for r in sesi.jalankan("MATCH (u:User) RETURN u.user_id AS user_id")}
    sql_user = {r[0] for r in conn.execute("SELECT user_id FROM users")}
    neo_edge = {(r["user_id_1"], r["user_id_2"]) for r in sesi.jalankan(read_query("relasi_semua.cypher"))}
    sql_edge = set(conn.execute("SELECT user_id_1, user_id_2 FROM friendships").fetchall())
    neo_hobi = {(r["user_id"], r["hobby"]) for r in sesi.jalankan(read_query("hobi_semua.cypher"))}
    sql_hobi = set(conn.execute("SELECT user_id, hobby FROM hobbies").fetchall())
    return {"user_hanya_neo4j": len(neo_user - sql_user), "user_hanya_sqlite": len(sql_user - neo_user),
            "edge_hanya_neo4j": len(neo_edge - sql_edge), "edge_hanya_sqlite": len(sql_edge - neo_edge),
            "hobi_hanya_neo4j": len(neo_hobi - sql_hobi), "hobi_hanya_sqlite": len(sql_hobi - neo_hobi),
            "jumlah_user": len(sql_user), "jumlah_edge": len(sql_edge), "jumlah_user_hobi": len(sql_hobi)}


def selisih_atribut(sesi: SesiCypher, conn) -> list[tuple]:
    """Atribut yang diduplikasi di node Neo4j (gender, age, region) vs kolom yang sama di SQLite, per user.

    Mengembalikan daftar (user_id, kolom, nilai_neo4j, nilai_sqlite) untuk setiap nilai yang berbeda; kosong = sinkron.
    """
    neo = {r["user_id"]: (r["gender"], r["age"], r["region"]) for r in sesi.jalankan(read_query("atribut_node.cypher"))}
    beda = []
    for uid, gender, umur, region in conn.execute("SELECT user_id, gender, age, region FROM users ORDER BY user_id"):
        punya_neo = neo.get(uid)
        if punya_neo is None:
            continue   # user tidak ada di Neo4j: dilaporkan oleh selisih_himpunan()
        for nama, nilai_neo, nilai_sql in zip(KOLOM_DUPLIKAT, punya_neo, (gender, umur, region)):
            if nilai_neo != nilai_sql:
                beda.append((uid, nama, nilai_neo, nilai_sql))
    return beda


def sinkron_atribut(sesi: SesiCypher, conn, user_ids: list[int] | None = None) -> int:
    """Salin gender/age/region dari SQLite (sumber kebenaran) ke node Neo4j; kosong di SQLite menghapus properti di Neo4j."""
    if user_ids is None:
        baris = conn.execute("SELECT user_id, gender, age, region FROM users").fetchall()
    else:
        baris = []
        for i in range(0, len(user_ids), 500):
            bagian = [int(u) for u in user_ids[i:i + 500]]
            baris += conn.execute(f"SELECT user_id, gender, age, region FROM users WHERE user_id IN ({','.join('?' * len(bagian))})",
                                  bagian).fetchall()
    rows = [{"user_id": u, "gender": g, "age": a, "region": r} for u, g, a, r in baris]
    for i in range(0, len(rows), 1000):
        sesi.jalankan("UNWIND $rows AS r MATCH (u:User {user_id: r.user_id}) "
                      "SET u.gender = r.gender, u.age = r.age, u.region = r.region", rows=rows[i:i + 1000])
    return len(rows)


def uji_drift(sesi: SesiCypher, conn) -> dict:
    """Suntik 3 ketidaksinkronan di Neo4j, pastikan terdeteksi persis, lalu perbaiki dari SQLite dan pastikan bersih.

    Yang diubah hanya node Neo4j (SQLite tidak disentuh), dan perbaikan dijalankan di blok finally sehingga graf
    selalu kembali seperti semula walaupun ada error di tengah.
    """
    sebelum = selisih_atribut(sesi, conn)
    kandidat = [r[0] for r in conn.execute(
        "SELECT user_id FROM users WHERE age IS NOT NULL AND gender IS NOT NULL ORDER BY user_id LIMIT 3")]
    terdeteksi, setelah, waktu_perbaikan = [], None, None
    try:
        sesi.jalankan("MATCH (u:User {user_id: $u}) SET u.age = u.age + 1", u=kandidat[0])
        sesi.jalankan("MATCH (u:User {user_id: $u}) SET u.gender = 1 - u.gender", u=kandidat[1])
        sesi.jalankan("MATCH (u:User {user_id: $u}) SET u.region = 'drift'", u=kandidat[2])
        terdeteksi = selisih_atribut(sesi, conn)
    finally:
        mulai = time.perf_counter()
        sinkron_atribut(sesi, conn, kandidat)
        waktu_perbaikan = (time.perf_counter() - mulai) * 1000
        setelah = selisih_atribut(sesi, conn)
    harapan = {(kandidat[0], "age"), (kandidat[1], "gender"), (kandidat[2], "region")}
    return {"sebelum": len(sebelum), "disuntik": 3, "terdeteksi": len(terdeteksi),
            "terdeteksi_tepat": {(u, k) for u, k, *_ in terdeteksi} == harapan, "setelah_perbaikan": len(setelah),
            "waktu_perbaikan_ms": waktu_perbaikan, "contoh": terdeteksi[:3]}


# --------------------------------------------------------------------------
# Biaya: lintas batas, penyimpanan
# --------------------------------------------------------------------------
def biaya_lintas_batas(sesi: SesiCypher, conn, hq, ukuran=(10, 100, 1000, 4505), ulangi: int = 5) -> pd.DataFrame:
    """Waktu mengambil profil N user dari SQLite (IN (...) + pandas) vs atribut yang sama dari node Neo4j."""
    semua = [r[0] for r in conn.execute("SELECT user_id FROM users ORDER BY user_id")]
    cy = "MATCH (u:User) WHERE u.user_id IN $ids RETURN u.user_id AS user_id, u.age AS age, u.gender AS gender, u.region AS region"
    baris = []
    for n in ukuran:
        ids = semua[:min(n, len(semua))]
        waktu, hasil, _ = ukur_bergantian({
            "sqlite": lambda ids=ids: hq._ambil_profil(conn, ids, ["age", "gender", "region"]),
            "neo4j": lambda ids=ids: pd.DataFrame(sesi.jalankan(cy, ids=ids))}, ulangi=ulangi, pemanasan=1)
        baris.append({"n_user": len(ids), "sqlite_ms": statistics.median(waktu["sqlite"]),
                      "neo4j_ms": statistics.median(waktu["neo4j"]), "baris_sqlite": len(hasil["sqlite"]),
                      "baris_neo4j": len(hasil["neo4j"])})
    return pd.DataFrame(baris)


def _ukuran_folder(folder: Path) -> int:
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) if folder.is_dir() else 0


def ukuran_penyimpanan(conn) -> dict:
    """Ukuran data di disk: berkas SQLite (+ tabel friendships bila ada) dan folder penyimpanan database Neo4j."""
    from neo4j_lokal import _home, _konfig   # pembaca NEO4J_HOME milik modul notebook
    hasil = {"sqlite_berkas_byte": SQLITE_PATH.stat().st_size}
    memori = sqlite3.connect(":memory:")   # tabel friendships sendirian di basis data baru -> ukurannya = halaman x ukuran halaman
    bangun_friendships(memori)
    hasil["sqlite_friendships_byte"] = (memori.execute("PRAGMA page_count").fetchone()[0]
                                        * memori.execute("PRAGMA page_size").fetchone()[0])
    memori.close()
    home = _home(_konfig())
    hasil["neo4j_store_byte"] = _ukuran_folder(home / "data" / "databases" / "neo4j") if home else None
    jumlah_user = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    hasil["nilai_atribut_duplikat"] = jumlah_user * len(KOLOM_DUPLIKAT)
    hasil["edge_duplikat_di_sqlite"] = conn.execute("SELECT COUNT(*) FROM friendships").fetchone()[0]
    return hasil


# --------------------------------------------------------------------------
# Skala: graf sintetis (model Barabasi-Albert) yang dimuat sementara ke Neo4j dan SQLite
# --------------------------------------------------------------------------
def graf_sintetis(n: int, m: int, seed: int = 42, timbal_balik: float = 0.7) -> list[tuple[int, int]]:
    """Edge berarah dari graf preferential attachment (Barabasi dan Albert, 1999): tiap edge diberi arah acak,
    dan dengan peluang `timbal_balik` ditambah arah sebaliknya (Pokec sampel: ±71% timbal balik)."""
    import networkx as nx
    graf, acak, edge = nx.barabasi_albert_graph(n, m, seed=seed), random.Random(seed), set()
    for u, v in graf.edges():
        a, b = (u + 1, v + 1) if acak.random() < 0.5 else (v + 1, u + 1)
        edge.add((a, b))
        if acak.random() < timbal_balik:
            edge.add((b, a))
    return sorted(edge)


def hapus_sintetis(sesi: SesiCypher) -> None:
    """Hapus semua node berlabel Syn (graf sintetis) dan indeksnya; node User/Hobby asli tidak disentuh."""
    while sesi.jalankan("MATCH (s:Syn) WITH s LIMIT 20000 DETACH DELETE s RETURN count(*) AS n")[0]["n"]:
        pass
    sesi.jalankan("DROP INDEX syn_uid IF EXISTS")


def _muat_sintetis(sesi: SesiCypher, n: int, edge: list[tuple[int, int]], batch: int = 10_000) -> None:
    sesi.jalankan("CREATE INDEX syn_uid IF NOT EXISTS FOR (s:Syn) ON (s.user_id)")
    sesi.jalankan("CALL db.awaitIndexes(300)")
    for i in range(1, n + 1, batch):
        sesi.jalankan("UNWIND range($a, $b) AS i CREATE (:Syn {user_id: i})", a=i, b=min(i + batch - 1, n))
    for i in range(0, len(edge), batch):
        sesi.jalankan("UNWIND $rows AS r MATCH (a:Syn {user_id: r[0]}) MATCH (b:Syn {user_id: r[1]}) "
                      "CREATE (a)-[:S_FRIEND]->(b)", rows=[list(e) for e in edge[i:i + batch]])


def uji_skala(sesi: SesiCypher, ukuran=(10_000, 40_000), m: int = 8, k: int = 3, ulangi: int = 5) -> pd.DataFrame:
    """Ulangi 'tepat k relasi' pada graf sintetis yang makin besar (dimuat sementara, dihapus lagi).

    Neo4j: label Syn, relasi S_FRIEND, dihapus di blok finally. SQLite: tabel di basis data memori (tidak menyentuh pokec.db).
    """
    baris = []
    conn = sqlite3.connect(":memory:")
    try:
        hapus_sintetis(sesi)   # sisa dari proses yang pernah terputus
        for n in ukuran:
            edge = graf_sintetis(n, m)
            mulai = time.perf_counter()
            bangun_friendships(conn, edge, "syn_friendships")
            muat_sql = (time.perf_counter() - mulai) * 1000
            mulai = time.perf_counter()
            _muat_sintetis(sesi, n, edge)
            muat_neo = (time.perf_counter() - mulai) * 1000
            derajat = sorted(Counter(a for a, _ in edge).items(), key=lambda kv: (-kv[1], kv[0]))
            uji = [derajat[0], derajat[int(len(derajat) * 0.10)], derajat[int(len(derajat) * 0.50)]]
            cy = cypher_k(k, "Syn", "S_FRIEND")
            pemanasan_neo4j(sesi, uji, 2.0, cypher=cy)
            for uid, deg in uji:
                r = tiga_cara_k_hop(sesi, conn, uid, k, ulangi, "syn_friendships", "Syn", "S_FRIEND")
                r.update(n_user=n, n_edge=len(edge), out_degree=deg, muat_sqlite_ms=muat_sql, muat_neo4j_ms=muat_neo)
                baris.append(r)
            hapus_sintetis(sesi)
    finally:
        hapus_sintetis(sesi)
        conn.close()
    return pd.DataFrame(baris)


# --------------------------------------------------------------------------
# Analisis
# --------------------------------------------------------------------------
def regresi_waktu_path(df: pd.DataFrame) -> dict:
    """Cocokkan waktu = a + b x jumlah_path untuk tiap mesin (kuadrat terkecil). b dalam mikrodetik per path, a dalam ms."""
    hasil = {}
    for nama, kolom in (("sqlite_join", "sqlite_join_ms"), ("neo4j_enum", "neo4j_enum_ms")):
        d = df.dropna(subset=[kolom])
        x, y = d["jumlah_path"].to_numpy(float), d[kolom].to_numpy(float)
        b, a = np.polyfit(x, y, 1)
        prediksi = a + b * x
        ss_res, ss_tot = float(((y - prediksi) ** 2).sum()), float(((y - y.mean()) ** 2).sum())
        hasil[nama] = {"a_ms": float(a), "b_mikrodetik_per_path": float(b * 1000), "r2": 1 - ss_res / ss_tot if ss_tot else float("nan"),
                       "n_titik": int(len(d))}
    return hasil


# --------------------------------------------------------------------------
# Ringkasan dan vonis hipotesis (dihitung dari data, bukan teks tetap)
# --------------------------------------------------------------------------
def _jumlah(df: pd.DataFrame, kolom_a: str, kolom_b: str, k: int | None = None) -> tuple[float, float, int]:
    """Jumlah waktu median dua kolom pada baris yang KEDUANYA terisi (supaya dibandingkan pada pekerjaan yang sama)."""
    d = df if k is None else df[df["k"] == k]
    d = d.dropna(subset=[kolom_a, kolom_b])
    return float(d[kolom_a].sum()), float(d[kolom_b].sum()), len(d)


def ringkasan_keluarga(h: dict) -> pd.DataFrame:
    """Satu baris per pasangan pertanyaan yang setara: waktu SQLite, waktu Neo4j, rasio (SQLite / Neo4j), pemenang, hasil sama.

    `h` berisi hasil keluarga_*: dasar (daftar dict), rekomendasi, khop, jalur, strategi (DataFrame). Rasio > 1 = Neo4j lebih cepat.
    """
    baris = []

    def tambah(keluarga, setara, sql_ms, neo_ms, sama, token_sql=None, token_cy=None, n=None):
        acuan = ("Cheng dkk. 2019" if keluarga.startswith(("Pencarian", "Agregasi")) else
                 "LDBC SNB Q10 (Erling dkk. 2015)" if keluarga.startswith("Rekomendasi") else
                 "LDBC SNB Q13; Miler dkk. 2014; Holsch dkk. 2017" if keluarga.startswith("Jalur") else
                 "Hassan dkk. 2018; Rodriguez dan Neubauer 2010" if keluarga.startswith("Teman tepat") else
                 "Backstrom dan Leskovec 2011; Hassan dkk. 2018")
        baris.append({"keluarga": keluarga, "setara": setara, "sqlite_ms": sql_ms, "neo4j_ms": neo_ms, "rasio": sql_ms / neo_ms,
                      "pemenang": "Neo4j" if neo_ms < sql_ms else "SQLite", "hasil_sama": bool(sama), "n": n,
                      "token_sql": token_sql, "token_cypher": token_cy, "acuan": acuan})

    berkas = {"pencarian_titik": ("pencarian_titik.sql", "pencarian_titik.cypher"),
              "agregasi_gender": ("agregasi_gender.sql", "agregasi_gender.cypher"),
              "agregasi_derajat": ("agregasi_derajat.sql", "agregasi_derajat.cypher")}
    for r in h.get("dasar", []):
        sql_f, cy_f = berkas[r["berkas_query"]]
        tambah(r["keluarga"], r["keterangan"], r["sqlite_ms"], r["neo4j_ms"], r["sama"], token_query(sql_f), token_query(cy_f))
    rek = h.get("rekomendasi")
    if rek is not None and len(rek):
        tambah("Rekomendasi teman (top-10)", f"jumlah {len(rek)} user uji", float(rek["sqlite_ms"].sum()), float(rek["neo4j_ms"].sum()),
               rek["sama"].all(), token_query("rekomendasi_teman.sql"), token_query("rekomendasi_teman_inti.cypher"), len(rek))
    kh = h.get("khop")
    if kh is not None and len(kh):
        for k in sorted(kh["k"].unique()):
            a, b, n = _jumlah(kh, "sqlite_distinct_ms", "neo4j_unik_ms", k)
            tambah(f"Teman tepat {k} relasi: himpunan unik", f"SQL DISTINCT per level vs Cypher pruning; jumlah {n} user", a, b,
                   kh[kh["k"] == k]["hasil_sama"].all(), token_query(teks=sql_distinct_k(int(k))),
                   token_query("teman_k_level_unik.cypher"), n)
        for k in sorted(kh[kh["k"] >= 2]["k"].unique()):
            a, b, n = _jumlah(kh, "sqlite_join_ms", "neo4j_enum_ms", k)
            if n:
                tambah(f"Teman tepat {k} relasi: semua path", f"SQL JOIN berulang vs Cypher count(p); jumlah {n} user", a, b,
                       kh[kh["k"] == k]["hasil_sama"].all(), token_query(teks=sql_join_k(int(k))),
                       token_query("teman_k_level.cypher"), n)
        a, b, n = _jumlah(kh, "sqlite_join_ms", "neo4j_unik_ms", 3)
        if n:
            tambah("Teman tepat 3 relasi: JOIN vs pruning", "SQL JOIN berulang vs Cypher tanpa count(p) (cara menulis yang paling umum)",
                   a, b, kh[kh["k"] == 3]["hasil_sama"].all(), token_query(teks=sql_join_k(3)),
                   token_query("teman_k_level_unik.cypher"), n)
    jl = h.get("jalur")
    if jl is not None and len(jl):
        tambah("Jalur terpendek (maks 8 relasi)", f"{len(jl)} pasangan user (sebagian tidak terhubung)", float(jl["sqlite_ms"].sum()),
               float(jl["neo4j_ms"].sum()), jl["sama"].all(), token_query("jalur_terpendek.sql"),
               token_query("jalur_terpendek.cypher"), len(jl))
    st = h.get("strategi")
    if st is not None and len(st):
        tambah("Teman dari teman + filter atribut", f"S1 semua di SQLite vs S2 semua di Neo4j; jumlah {len(st)} user",
               float(st["s1_sql_ms"].sum()), float(st["s2_neo4j_ms"].sum()), st["sama"].all(),
               token_query("fof_filter.sql"), token_query("fof_filter.cypher"), len(st))
    return pd.DataFrame(baris)


def vonis_hipotesis(h: dict, tabel_tes: pd.DataFrame) -> pd.DataFrame:
    """Bandingkan data dengan lima hipotesis di Bab 1: DIDUKUNG, SEBAGIAN, atau TIDAK DIDUKUNG, lengkap dengan angkanya."""
    ring = h.get("ringkasan")
    baris = []

    def lulus(prefiks: tuple) -> tuple:
        d = tabel_tes[tabel_tes["kelompok"].str.startswith(prefiks)]
        gagal = int((d["hasil"] == "GAGAL").sum())
        return len(d) > 0 and gagal == 0, f"{len(d) - gagal}/{len(d)} tes lulus"

    ok, ket = lulus(("1.", "3.", "3b."))
    baris.append(("H1", "Dua basis data konsisten dan hasil gabungan sama persis dengan jawaban kunci",
                  "DIDUKUNG" if ok else "TIDAK DIDUKUNG", ket))
    if ring is not None and len(ring):
        sql_tok, cy_tok = ring["token_sql"].dropna(), ring["token_cypher"].dropna()
        baris.append(("H2", "Pertanyaan yang sama dijawab identik; beda di kinerja dan kemudahan menulis query",
                      "DIDUKUNG" if bool(ring["hasil_sama"].all()) else "TIDAK DIDUKUNG",
                      f"{int(ring['hasil_sama'].sum())}/{len(ring)} pasangan query identik; median token SQL "
                      f"{sql_tok.median():.0f} vs Cypher {cy_tok.median():.0f}"))

        def rasio(nama):
            r = ring[ring["keluarga"] == nama]
            return float(r["rasio"].iloc[0]) if len(r) else None

        naif = rasio("Teman tepat 3 relasi: JOIN vs pruning")
        unik = {k: rasio(f"Teman tepat {k} relasi: himpunan unik") for k in (2, 3, 4)}
        semua = {k: rasio(f"Teman tepat {k} relasi: semua path") for k in (2, 3, 4)}
        jalur = rasio("Jalur terpendek (maks 8 relasi)")

        def lebih(v, batas=1.0):
            return v is not None and v > batas

        menang_k2 = lebih(unik[2]) and lebih(semua[2])
        menang_k34 = all(lebih(v) for v in (unik[3], unik[4], semua[3], semua[4], naif, jalur))
        tumbuh = (unik[2] is not None and unik[3] is not None and unik[4] is not None and unik[2] < unik[3] < unik[4]
                  and semua[2] is not None and semua[3] is not None and semua[4] is not None and semua[2] < semua[3] < semua[4])

        def f(v):
            return "-" if v is None else f"{v:.2f}\u00d7"

        if menang_k2 and menang_k34 and tumbuh:
            hasil_h3 = "DIDUKUNG"
        elif menang_k34 and tumbuh:
            hasil_h3 = "SEBAGIAN"          # unggul hanya mulai k >= 3 (di k <= 2 SQLite lebih cepat)
        elif lebih(naif) or lebih(jalur):
            hasil_h3 = "SEBAGIAN"
        else:
            hasil_h3 = "TIDAK DIDUKUNG"
        ket_skala = ""
        sk = h.get("skala")
        if sk is not None and len(sk):
            hub = sk.sort_values("jumlah_path", ascending=False).groupby("n_edge").head(1).sort_values("n_edge")
            ket_skala = "; hub graf sintetis (SQL/Neo4j): " + ", ".join(
                f"{int(r.n_edge):,} edge: semua path {r.sqlite_join_ms / r.neo4j_enum_ms:.2f}\u00d7, unik {r.sqlite_distinct_ms / r.neo4j_unik_ms:.2f}\u00d7"
                for r in hub.itertuples())
        baris.append(("H3", "Neo4j lebih cepat untuk penelusuran multi-hop, dan selisihnya membesar dengan kedalaman dan jumlah path",
                      hasil_h3,
                      f"rasio SQLite/Neo4j (di atas 1 = Neo4j lebih cepat): himpunan unik k=2 {f(unik[2])}, k=3 {f(unik[3])}, k=4 {f(unik[4])}; "
                      f"semua path k=2 {f(semua[2])}, k=3 {f(semua[3])}, k=4 {f(semua[4])}; JOIN vs pruning k=3 {f(naif)}; "
                      f"jalur terpendek {f(jalur)}{ket_skala}"))
        titik, attr, deg = ring.iloc[0], ring.iloc[1], ring.iloc[2]
        h4 = all(r["pemenang"] == "SQLite" for r in (titik, attr, deg))
        baris.append(("H4", "SQLite setara atau lebih cepat untuk pencarian titik dan agregasi atribut",
                      "DIDUKUNG" if h4 else "TIDAK DIDUKUNG",
                      f"rasio SQLite/Neo4j: pencarian titik {titik['rasio']:.3f}, agregasi atribut {attr['rasio']:.3f}, "
                      f"agregasi struktur {deg['rasio']:.3f} (di bawah 1 = SQLite lebih cepat)"))
    d = h.get("drift")
    if d:
        ok5 = bool(d["terdeteksi_tepat"]) and d["setelah_perbaikan"] == 0
        baris.append(("H5", "Duplikasi atribut menimbulkan risiko ketidaksinkronan yang dapat dideteksi otomatis",
                      "DIDUKUNG" if ok5 else "TIDAK DIDUKUNG",
                      f"{d['disuntik']} ketidaksinkronan disuntik, {d['terdeteksi']} terdeteksi (tepat: {d['terdeteksi_tepat']}), "
                      f"{d['setelah_perbaikan']} tersisa setelah perbaikan"))
    return pd.DataFrame(baris, columns=["hipotesis", "pernyataan", "hasil", "bukti"])


def jawaban_dosen(h: dict, tabel_tes: pd.DataFrame) -> list[str]:
    """Jawaban atas pertanyaan dosen (apakah graph database dapat dikombinasikan dengan relational database biasa), disusun dari data."""
    baris: list[str] = []
    inti = tabel_tes[tabel_tes["kelompok"].str.startswith(("1.", "2.", "3.", "3b.", "4."))]
    lulus_inti, total_inti = int((inti["hasil"] == "LULUS").sum()), len(inti)
    ring = h.get("ringkasan")
    sama = ring is not None and bool(ring["hasil_sama"].all())
    if lulus_inti == total_inti and sama:
        baris.append("JAWABAN: YA. Graph database (Neo4j) dapat dikombinasikan dengan relational database biasa (SQLite), "
                     "dan hasil gabungannya benar.")
    else:
        baris.append(f"JAWABAN: BELUM TERBUKTI PENUH. {total_inti - lulus_inti} dari {total_inti} tes inti gagal atau ada hasil yang berbeda.")
    baris.append(f"Bukti kebenaran: {lulus_inti}/{total_inti} tes inti lulus (konsistensi, sinkronisasi, fungsi hybrid, kesetaraan hasil); "
                 f"{0 if ring is None else int(ring['hasil_sama'].sum())}/{0 if ring is None else len(ring)} pasangan query memberi hasil "
                 "identik di SQLite dan Neo4j.")
    if ring is not None and len(ring):
        neo = ring[ring["pemenang"] == "Neo4j"]
        sql = ring[ring["pemenang"] == "SQLite"]
        baris.append("Pembagian tugas, Neo4j lebih cepat pada: " +
                     ("; ".join(f"{r.keluarga} ({r.rasio:.1f}×)" for r in neo.itertuples()) or "(tidak ada)") + ".")
        baris.append("Pembagian tugas, SQLite lebih cepat pada: " +
                     ("; ".join(f"{r.keluarga} ({1 / r.rasio:.1f}×)" for r in sql.itertuples()) or "(tidak ada)") + ".")
    st, lb, ov, dr = h.get("strategi"), h.get("lintas_batas"), h.get("overhead"), h.get("drift")
    biaya = []
    if st is not None and len(st):
        biaya.append(f"strategi hybrid (id dari Neo4j, filter di SQLite) {st['s3_hybrid_ms'].sum() / st['s1_sql_ms'].sum():.0f}× "
                     f"lebih lambat daripada semua-di-SQLite dan {st['s3_hybrid_ms'].sum() / st['s2_neo4j_ms'].sum():.0f}× daripada "
                     "semua-di-Neo4j, tetapi tidak menduplikasi atribut")
    if lb is not None and len(lb):
        akhir = lb.iloc[-1]
        biaya.append(f"mengambil atribut {int(akhir['n_user']):,} user: SQLite {akhir['sqlite_ms']:.1f} ms vs Neo4j {akhir['neo4j_ms']:.1f} ms")
    if ov:
        biaya.append(f"biaya tetap per panggilan: SQLite {ov['sqlite_ms']:.3f} ms vs Neo4j {ov['neo4j_ms']:.2f} ms")
    if dr:
        biaya.append(f"atribut yang diduplikasi bisa tidak sinkron: {dr['disuntik']} penyimpangan disuntik, {dr['terdeteksi']} terdeteksi, "
                     f"diperbaiki dalam {dr['waktu_perbaikan_ms']:.0f} ms")
    if biaya:
        baris.append("Biaya kombinasi: " + "; ".join(biaya) + ".")
    baris.append("Batas: sampel 4.505 user dan 72.004 relasi di satu komputer; angka kinerja berlaku untuk skala ini "
                 "(uji graf sintetis hanya sampai ±0,5 juta relasi).")
    return baris


# --------------------------------------------------------------------------
# Karakter sampel dibanding seluruh Pokec
# --------------------------------------------------------------------------
def profil_graf(user_ids: list[int], pasangan: list[tuple[int, int]], sumber: int = 150, seed: int = 11) -> dict:
    """Ukuran struktur graf sampel (resiprositas, derajat, klasterisasi, diameter perkiraan) untuk dibandingkan dengan SNAP.

    Diameter perkiraan = jarak terjauh dari `sumber` titik acak pada komponen terhubung terbesar (graf tak berarah), jadi batas bawah
    diameter; diameter efektif = persentil ke-90 semua jarak yang teramati.
    """
    import networkx as nx
    g = nx.DiGraph()
    g.add_nodes_from(user_ids)
    g.add_edges_from(pasangan)
    tak_berarah = g.to_undirected()
    komponen = max(nx.connected_components(tak_berarah), key=len)
    acak = random.Random(seed)
    jarak, terjauh = [], 0
    for s0 in acak.sample(sorted(komponen), min(sumber, len(komponen))):
        d = nx.single_source_shortest_path_length(tak_berarah, s0)
        jarak.extend(v for v in d.values() if v > 0)
        terjauh = max(terjauh, max(d.values()))
    keluar = [d for _, d in g.out_degree()]
    return {"user": g.number_of_nodes(), "edge": g.number_of_edges(), "resiprositas": nx.reciprocity(g),
            "terisolasi": sum(1 for n in g if g.degree(n) == 0) / g.number_of_nodes(),
            "median_out_degree": float(np.median(keluar)), "maks_out_degree": int(max(keluar)),
            "klasterisasi_rata2": nx.average_clustering(tak_berarah), "komponen_terbesar": len(komponen) / g.number_of_nodes(),
            "diameter_perkiraan": int(terjauh), "diameter_efektif_90": float(np.percentile(jarak, 90))}
