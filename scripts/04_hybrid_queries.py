"""Langkah 4 - Query hybrid: SQLite untuk ATRIBUT, Neo4j untuk HUBUNGAN, Python sebagai penyambung.

Pola yang dipakai di semua fungsi:
  1. Neo4j menjawab pertanyaan tentang struktur ("siapa terhubung dengan siapa") dan
     mengembalikan daftar user_id (+ angka seperti jumlah teman bersama).
  2. Python mengambil user_id itu, lalu bertanya ke SQLite "siapa mereka?" (umur,
     pendidikan, dst.) lewat satu query IN (...).
  3. Hasil digabung jadi satu DataFrame.

Setiap query ada di folder queries/ (bisa ditempel langsung ke Neo4j Browser).
PRASYARAT: Neo4j Desktop sudah di-Start, .env terisi, script 02 dan 03 sudah dijalankan.
"""
from __future__ import annotations

import argparse
import statistics
import time
from collections import defaultdict
from contextlib import contextmanager

import pandas as pd

from common import (
    banner,
    connect_neo4j,
    connect_sqlite,
    fail,
    friendly_neo4j_errors,
    normalize_hobby,
    read_edges_csv,
    read_query,
)

PROFIL_RINGKAS = ["age", "gender", "region", "completed_level_of_education"]


# --------------------------------------------------------------------------
# Helper
# --------------------------------------------------------------------------
@contextmanager
def _koneksi():
    """Buka Neo4j dan SQLite sekaligus, tutup keduanya otomatis.

    Database: keduanya. Error Neo4j yang umum diubah jadi pesan ramah.
    """
    driver = connect_neo4j()
    conn = connect_sqlite()
    try:
        with friendly_neo4j_errors():
            yield driver, conn
    finally:
        conn.close()
        driver.close()


def _cypher(driver, nama_file: str, **params) -> list[dict]:
    """Jalankan query dari folder queries/ di Neo4j, kembalikan list of dict.

    Database: Neo4j (read transaction).
    """
    query = read_query(nama_file)
    with driver.session() as session:
        return session.execute_read(lambda tx: [record.data() for record in tx.run(query, **params)])


def _ambil_profil(conn, user_ids, kolom: list[str] | None = None) -> pd.DataFrame:
    """Ambil profil user dari tabel users (kolom=None -> semua kolom).

    Database: SQLite. Dipecah per 500 id supaya batas jumlah parameter SQLite tak terlampaui.
    """
    ids = [int(u) for u in user_ids]
    select = "*" if kolom is None else ", ".join(["user_id", *kolom])
    potongan = []
    for i in range(0, len(ids), 500):
        bagian = ids[i:i + 500]
        sql = f"SELECT {select} FROM users WHERE user_id IN ({','.join('?' * len(bagian))})"
        potongan.append(pd.read_sql_query(sql, conn, params=bagian))
    profil = pd.concat(potongan, ignore_index=True) if potongan else pd.read_sql_query(
        f"SELECT {select} FROM users WHERE 0", conn)
    for kolom_int in ("age", "gender", "public", "completion_percentage"):
        if kolom_int in profil:
            profil[kolom_int] = profil[kolom_int].astype("Int64")
    return profil


def _gabung_profil(hasil: pd.DataFrame, conn, kolom: list[str] | None) -> pd.DataFrame:
    """Gabungkan hasil Neo4j dengan profil SQLite (left join; urutan dari Neo4j dipertahankan)."""
    return hasil.merge(_ambil_profil(conn, hasil["user_id"], kolom), on="user_id", how="left")


def _tampil(df: pd.DataFrame, lebar: int = 28) -> str:
    """Format DataFrame untuk dicetak: NULL jadi '-', gender jadi label, teks panjang dipotong."""
    out = df.copy()
    if "gender" in out:
        out["gender"] = out["gender"].map({1: "pria", 0: "wanita"})
    for kolom in out.columns:
        if pd.api.types.is_numeric_dtype(out[kolom]):  # angka dibiarkan (Int64 tidak boleh berubah jadi float)
            continue
        out[kolom] = out[kolom].map(lambda v: ", ".join(map(str, v)) if isinstance(v, list) else v)
        out[kolom] = out[kolom].map(lambda v: v[:lebar - 2] + ".." if isinstance(v, str) and len(v) > lebar else v)
    return out.astype(object).where(out.notna(), "-").to_string(index=False)


def _derajat_semua(driver) -> pd.DataFrame:
    """Derajat (out/in/total) semua user dari Neo4j, terurut dari yang paling terhubung."""
    derajat = pd.DataFrame(_cypher(driver, "user_paling_terhubung.cypher", limit=10**9))
    if derajat.empty:
        fail("Graph di Neo4j masih kosong. Jalankan dulu: python scripts/03_sync_to_neo4j.py")
    return derajat


def _pilih_user_demo(driver) -> int:
    """User contoh: out-degree di persentil ke-75 (cukup banyak teman, tapi bukan hub ekstrem)."""
    derajat = _derajat_semua(driver)
    aktif = derajat[derajat["out_degree"] > 0].sort_values(["out_degree", "user_id"], ascending=[False, True])
    return int(aktif.iloc[int(len(aktif) * 0.25)]["user_id"])


# --------------------------------------------------------------------------
# a) Rekomendasi teman
# --------------------------------------------------------------------------
def rekomendasi_teman(user_id: int, limit: int = 10) -> pd.DataFrame:
    """Rekomendasikan "teman dari teman" yang belum berteman langsung dengan user_id.

    Database: KEDUANYA. Neo4j mencari kandidat dan menghitung teman bersama (traversal
    2 hop, inti kekuatan graph); SQLite memberi detail profil (umur, region, pendidikan)
    yang memang tidak disimpan di graph. Dibagi begini agar graph tetap ramping.
    """
    with _koneksi() as (driver, conn):
        baris = _cypher(driver, "rekomendasi_teman.cypher", user_id=int(user_id), limit=int(limit))
        hasil = pd.DataFrame(baris, columns=["user_id", "teman_bersama", "lewat_teman"])
        return _gabung_profil(hasil, conn, PROFIL_RINGKAS)


# --------------------------------------------------------------------------
# b) Komunitas hobi
# --------------------------------------------------------------------------
def _bentuk_klaster(anggota: list[int], pasangan: list[tuple[int, int]], min_size: int) -> list[list[int]]:
    """Kelompokkan anggota yang saling terhubung (komponen terhubung, union-find sederhana).

    Database: tidak ada (murni Python). Cukup traversal sederhana, tanpa algoritma
    community detection.
    """
    induk = {u: u for u in anggota}

    def cari(x: int) -> int:
        while induk[x] != x:
            induk[x] = induk[induk[x]]
            x = induk[x]
        return x

    for a, b in pasangan:
        induk[cari(a)] = cari(b)
    kelompok = defaultdict(list)
    for u in anggota:
        kelompok[cari(u)].append(u)
    return sorted((sorted(k) for k in kelompok.values() if len(k) >= min_size), key=lambda k: (-len(k), k[0]))


def cari_komunitas_hobi(hobby_name: str, min_size: int = 3) -> pd.DataFrame:
    """Cari klaster user yang berbagi hobi hobby_name DAN saling berteman, lalu perkaya dengan profil.

    Database: KEDUANYA. Neo4j menjawab dua hal: siapa pemilik hobi itu dan siapa di antara
    mereka yang berteman. Python merangkai pasangan itu jadi klaster (komponen terhubung);
    SQLite menambah profil tiap anggota. Klaster di bawah min_size anggota diabaikan.
    Satu baris hasil = satu anggota klaster (klaster 1 = yang terbesar).
    """
    kolom = ["klaster", "ukuran_klaster", "user_id", "teman_dalam_klaster", *PROFIL_RINGKAS]
    hobi = normalize_hobby(hobby_name)
    with _koneksi() as (driver, conn):
        anggota = [r["user_id"] for r in _cypher(driver, "komunitas_hobi_anggota.cypher", hobby=hobi)]
        if not anggota:
            contoh = [r[0] for r in conn.execute(
                "SELECT hobby FROM hobbies GROUP BY hobby ORDER BY COUNT(*) DESC LIMIT 8")]
            print(f"  Hobi '{hobi}' tidak ditemukan. Contoh hobi yang ada: {', '.join(contoh)}")
            return pd.DataFrame(columns=kolom)
        pasangan = [(r["user_a"], r["user_b"]) for r in _cypher(driver, "komunitas_hobi_koneksi.cypher", hobby=hobi)]

        tetangga = defaultdict(set)
        for a, b in pasangan:
            tetangga[a].add(b)
            tetangga[b].add(a)
        baris = [
            (nomor, len(isi), u, len(tetangga[u]))
            for nomor, isi in enumerate(_bentuk_klaster(anggota, pasangan, min_size), start=1)
            for u in sorted(isi, key=lambda x: (-len(tetangga[x]), x))
        ]
        hasil = pd.DataFrame(baris, columns=kolom[:4])
        hasil = _gabung_profil(hasil, conn, PROFIL_RINGKAS)
    hasil.attrs.update(hobi=hobi, pemilik_hobi=len(anggota), min_size=min_size)
    return hasil


def ringkas_klaster(komunitas: pd.DataFrame) -> pd.DataFrame:
    """Ringkas hasil cari_komunitas_hobi() jadi satu baris per klaster.

    Database: tidak ada (murni pandas atas data yang sudah digabung dari Neo4j + SQLite):
    ukuran klaster, umur rata-rata, jumlah pria/wanita, dan pendidikan terbanyak.
    """
    return komunitas.groupby("klaster").agg(
        anggota=("user_id", "size"),
        umur_rata2=("age", lambda s: round(float(s.dropna().astype(float).mean()), 1) if s.notna().any() else None),
        pria=("gender", lambda s: int((s == 1).sum())),
        wanita=("gender", lambda s: int((s == 0).sum())),
        pendidikan_terbanyak=("completed_level_of_education",
                              lambda s: s.mode().iloc[0] if s.notna().any() else None),
    ).reset_index()


# --------------------------------------------------------------------------
# c) User paling terhubung
# --------------------------------------------------------------------------
def user_paling_terhubung(limit: int = 10) -> pd.DataFrame:
    """Daftar `limit` user dengan degree centrality tertinggi, lengkap dengan profil.

    Database: KEDUANYA. Neo4j menghitung derajat (jumlah relasi FRIEND masuk + keluar)
    karena itu operasi native graph; SQLite memberi profil lengkap (semua kolom tabel users).
    """
    with _koneksi() as (driver, conn):
        baris = _cypher(driver, "user_paling_terhubung.cypher", limit=int(limit))
        hasil = pd.DataFrame(baris, columns=["user_id", "out_degree", "in_degree", "total_degree"])
        return _gabung_profil(hasil, conn, None)


# --------------------------------------------------------------------------
# (bonus) Hobi sama tapi belum berteman
# --------------------------------------------------------------------------
def rekomendasi_hobi_sama(user_id: int, limit: int = 10) -> pd.DataFrame:
    """User dengan hobi paling mirip dengan user_id tetapi belum berteman dengannya.

    Database: KEDUANYA. Neo4j: user -> Hobby <- user, dikurangi yang sudah berteman;
    SQLite: profil. Inilah alasan hobi dimodelkan sebagai node, bukan kolom teks.
    """
    with _koneksi() as (driver, conn):
        baris = _cypher(driver, "rekomendasi_hobi_sama.cypher", user_id=int(user_id), limit=int(limit))
        hasil = pd.DataFrame(baris, columns=["user_id", "hobi_sama", "hobi"])
        return _gabung_profil(hasil, conn, PROFIL_RINGKAS)


# --------------------------------------------------------------------------
# d) Benchmark multi-hop: SQL JOIN vs Cypher
# --------------------------------------------------------------------------
def _bangun_tabel_friendships(conn) -> int:
    """Buat tabel friendships di SQLite khusus untuk benchmark (salinan edges_sample.csv).

    Database: SQLite. Tabel ini duplikat dari graph di Neo4j; sengaja dibuat HANYA di sini
    supaya SQL mendapat kesempatan yang adil: PRIMARY KEY (user_id_1, user_id_2) = index
    yang dipakai tiap JOIN. Dibuat ulang setiap kali agar selalu sama dengan CSV.
    """
    edges = read_edges_csv()
    conn.executescript("""
        DROP TABLE IF EXISTS friendships;
        CREATE TABLE friendships (
            user_id_1 INTEGER NOT NULL,
            user_id_2 INTEGER NOT NULL,
            PRIMARY KEY (user_id_1, user_id_2)
        ) WITHOUT ROWID;
    """)
    conn.executemany("INSERT INTO friendships VALUES (?, ?)", edges.to_numpy().tolist())
    conn.commit()
    conn.execute("ANALYZE friendships")
    return len(edges)


def _pilih_user_uji(driver, jumlah: int) -> list[tuple[int, int]]:
    """Pilih user uji dari yang paling banyak teman sampai yang sedang-sedang saja.

    Database: Neo4j (derajat). Bentuk graph sosial itu timpang (sedikit hub, banyak
    user biasa), jadi satu user saja tidak mewakili; kita uji beberapa tingkat.
    """
    derajat = _derajat_semua(driver)
    aktif = derajat[derajat["out_degree"] > 0].sort_values(["out_degree", "user_id"], ascending=[False, True])
    pecahan = [0.0, 0.01, 0.10, 0.25, 0.50, 0.75, 0.90][:jumlah]
    dipilih: dict[int, int] = {}
    for p in pecahan:
        baris = aktif.iloc[min(int(len(aktif) * p), len(aktif) - 1)]
        dipilih.setdefault(int(baris["user_id"]), int(baris["out_degree"]))
    return list(dipilih.items())


def bandingkan_performa_query(jumlah_user: int = 5, ulangi: int = 5, pemanasan: float = 3.0) -> pd.DataFrame:
    """Bandingkan waktu "teman dari teman dari teman" (3 hop): SQL JOIN berulang vs Cypher.

    Database: KEDUANYA, dan di sini mereka dipertandingkan pada pertanyaan yang SAMA:
      * SQLite : 3 self-JOIN pada tabel friendships ber-index (queries/teman_3_level.sql)
      * Neo4j  : path variable-length [:FRIEND*3]    (queries/teman_3_level.cypher)
      * bonus  : SQL yang ditulis ulang dengan DISTINCT per level, sebagai pembanding
                 yang adil (queries/teman_3_level_dioptimalkan.sql)
    Sebelum mengukur ada pemanasan (tidak diukur): Cypher dijalankan keliling semua user uji
    selama `pemanasan` detik karena JVM yang baru menyala masih dingin, plus 2 putaran SQL per
    user. Lalu tiap user diukur `ulangi` kali, bergantian antar ketiga query, diambil median.
    Jadi yang dibandingkan adalah kinerja setelah hangat; query pertama di server yang baru
    menyala jauh lebih lambat. Hitungan dan checksum hasil harus sama persis.
    Waktu Neo4j = end-to-end dari Python (termasuk kirim-terima lewat Bolt), sama seperti
    sisi SQLite yang end-to-end dari Python.
    """
    sql = read_query("teman_3_level.sql")
    sql_dioptimalkan = read_query("teman_3_level_dioptimalkan.sql")
    sql_jumlah_path = read_query("teman_3_level_jumlah_path.sql")
    cypher = read_query("teman_3_level.cypher")
    with _koneksi() as (driver, conn):
        mulai = time.perf_counter()
        n_edge = _bangun_tabel_friendships(conn)
        print(f"  Tabel friendships dibuat di SQLite: {n_edge:,} baris ({time.perf_counter() - mulai:.2f} dtk)")
        rencana = " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, {"user_id": 0}))
        print(f"  Rencana SQLite: {rencana}")

        uji = _pilih_user_uji(driver, jumlah_user)
        baris = []
        with driver.session() as session:
            def jalankan_sql(query, uid):
                return tuple(conn.execute(query, {"user_id": uid}).fetchone())

            def jalankan_cypher(uid):
                hasil = session.run(cypher, user_id=uid)
                record = hasil.single()
                return (record["total"], record["checksum"]), hasil.consume()

            def ukur(fungsi):
                mulai = time.perf_counter()
                nilai = fungsi()
                return nilai, (time.perf_counter() - mulai) * 1000

            # Pemanasan Neo4j: JVM yang baru menyala itu dingin (query pertama bisa makan >1 detik, lalu
            # membaik bertahap lewat JIT), jadi Cypher dijalankan keliling semua user uji selama `pemanasan`
            # detik. SQLite tidak punya JIT; 2 putaran per user cukup untuk mengisi cache halaman.
            akhir = time.perf_counter() + pemanasan
            putaran = 0
            while time.perf_counter() < akhir:
                jalankan_cypher(uji[putaran % len(uji)][0])
                putaran += 1
            for uid, _ in uji:
                for _ in range(2):
                    jalankan_sql(sql, uid)
                    jalankan_sql(sql_dioptimalkan, uid)

            for uid, out_degree in uji:
                t_join, t_neo, t_server, t_opt = [], [], [], []
                for _ in range(ulangi):
                    hasil_join, ms = ukur(lambda: jalankan_sql(sql, uid))
                    t_join.append(ms)
                    (hasil_neo, ringkasan), ms = ukur(lambda: jalankan_cypher(uid))
                    t_neo.append(ms)
                    t_server.append((ringkasan.result_available_after or 0) + (ringkasan.result_consumed_after or 0))
                    hasil_opt, ms = ukur(lambda: jalankan_sql(sql_dioptimalkan, uid))
                    t_opt.append(ms)
                baris.append({
                    "user_id": uid,
                    "out_degree": out_degree,
                    "jumlah_path": jalankan_sql(sql_jumlah_path, uid)[0],  # hanya penjelasan, tidak diukur
                    "teman_3_level": hasil_join[0],
                    "sqlite_join_ms": statistics.median(t_join),
                    "neo4j_ms": statistics.median(t_neo),
                    "neo4j_server_ms": statistics.median(t_server),
                    "hasil_sama": hasil_join == hasil_neo,
                    "sqlite_distinct_ms": statistics.median(t_opt),
                    "distinct_sama": hasil_opt == hasil_neo,
                })
    hasil = pd.DataFrame(baris)
    hasil.insert(7, "join_per_neo4j", hasil["sqlite_join_ms"] / hasil["neo4j_ms"])
    return hasil


def _ringkas_benchmark(hasil: pd.DataFrame, ulangi: int) -> None:
    tampil = hasil.drop(columns=["hasil_sama", "distinct_sama"]).copy()
    for kolom in ("sqlite_join_ms", "neo4j_ms", "neo4j_server_ms", "sqlite_distinct_ms"):
        tampil[kolom] = tampil[kolom].map(lambda v: f"{v:.2f}")
    tampil["join_per_neo4j"] = tampil["join_per_neo4j"].map(lambda v: f"{v:.2f}x")
    print("\n" + tampil.to_string(index=False))
    print(f"\n  Median dari {ulangi} pengukuran per user, dalam milidetik. join_per_neo4j > 1 berarti Neo4j lebih cepat.")
    print("  jumlah_path = banyaknya path 3-relasi yang disusuri JOIN berulang; teman_3_level = user unik hasilnya.")
    print("  neo4j_ms = end-to-end dari Python; neo4j_server_ms = waktu eksekusi di sisi server saja.")
    print("  sqlite_distinct_ms = BONUS: SQL yang ditulis ulang (DISTINCT per level), bukan bagian perbandingan utama.")
    _kesimpulan_benchmark(hasil)


def _kesimpulan_benchmark(hasil: pd.DataFrame) -> None:
    """Cetak kecocokan hasil dan kesimpulan yang dihitung dari angka benchmark (bukan teks tetap)."""
    if hasil["hasil_sama"].all():
        print("\n  Hasil SQL JOIN berulang dan Cypher identik untuk semua user uji (jumlah + checksum).")
    else:
        print("\n  PERINGATAN: hasil SQL JOIN berulang dan Cypher BERBEDA untuk sebagian user - waktu tidak sebanding.")
    total_join, total_neo = hasil["sqlite_join_ms"].sum(), hasil["neo4j_ms"].sum()
    total_opt = hasil["sqlite_distinct_ms"].sum()
    if total_neo < total_join:
        print(f"  KESIMPULAN: total {total_neo:.1f} ms (Neo4j) vs {total_join:.1f} ms (SQLite JOIN berulang) "
              f"-> Neo4j {total_join / total_neo:.1f}x lebih cepat pada graph ini.")
    else:
        print(f"  KESIMPULAN: total {total_join:.1f} ms (SQLite JOIN berulang) vs {total_neo:.1f} ms (Neo4j) "
              f"-> SQLite {total_neo / total_join:.1f}x lebih cepat pada graph ini.")
    print(f"  BONUS     : SQL yang dioptimalkan total {total_opt:.1f} ms = {total_opt / total_neo:.2f}x waktu Neo4j "
          f"(hasil sama dengan Neo4j untuk {int(hasil['distinct_sama'].sum())}/{len(hasil)} user).")
    print("  Artinya: selisih terutama datang dari SQL JOIN berulang yang menyusuri SEMUA path. Query Cypher ini hanya")
    print("  meminta user unik di ujung, sehingga Neo4j boleh memangkas (VarLengthExpand(Pruning)) dan tidak menyusuri semua")
    print("  path; di SQL kita harus tahu trik DISTINCT per level untuk hal yang sama. Kalau Cypher juga diminta menghitung")
    print("  path (count(p)), kerjanya sama dengan JOIN dan selisihnya kecil. Perbandingan yang memisahkan kedua pasangan")
    print("  itu, juga untuk 1-4 relasi dan graf yang lebih besar, ada di notebooks/1_tes_semua.ipynb (Langkah 6 dan 8).")


# --------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Demo query hybrid SQLite + Neo4j.")
    parser.add_argument("--user-id", type=int, help="user untuk demo rekomendasi (default: dipilih otomatis)")
    parser.add_argument("--hobby", help="hobi untuk demo komunitas (default: hobi terpopuler)")
    parser.add_argument("--limit", type=int, default=10, help="jumlah baris hasil (default 10)")
    parser.add_argument("--ulangi", type=int, default=5, help="pengulangan pengukuran benchmark (default 5)")
    parser.add_argument("--pemanasan", type=float, default=3.0,
                        help="lama pemanasan Neo4j sebelum benchmark diukur, dalam detik (default 3)")
    parser.add_argument("--skip-benchmark", action="store_true", help="lewati fungsi (d)")
    args = parser.parse_args()
    if args.limit < 1 or args.ulangi < 1 or args.pemanasan < 0:
        fail("--limit dan --ulangi harus >= 1, --pemanasan harus >= 0")

    with _koneksi() as (driver, conn):
        user_id = args.user_id or _pilih_user_demo(driver)
        hobi = normalize_hobby(args.hobby) if args.hobby else conn.execute(
            "SELECT hobby FROM hobbies GROUP BY hobby ORDER BY COUNT(*) DESC, hobby LIMIT 1").fetchone()[0]
        profil = _ambil_profil(conn, [user_id], PROFIL_RINGKAS)
        derajat = _derajat_semua(driver).set_index("user_id")
    if user_id not in derajat.index:
        fail(f"user_id {user_id} tidak ada di graph.")
    print(f"User demo: {user_id} | out-degree {derajat.loc[user_id, 'out_degree']}, "
          f"in-degree {derajat.loc[user_id, 'in_degree']}")
    print(_tampil(profil))

    banner(f"a) rekomendasi_teman({user_id}) - teman dari teman yang belum berteman")
    hasil = rekomendasi_teman(user_id, args.limit)
    print(_tampil(hasil) if len(hasil) else "  (tidak ada kandidat)")

    banner(f"b) cari_komunitas_hobi('{hobi}') - klaster user sehobi yang saling berteman")
    komunitas = cari_komunitas_hobi(hobi)
    if len(komunitas):
        info = komunitas.attrs
        ringkas = ringkas_klaster(komunitas)
        print(f"  {info['pemilik_hobi']:,} user punya hobi ini; {len(komunitas):,} di antaranya tergabung dalam "
              f"{len(ringkas)} klaster (>= {info['min_size']} anggota yang saling terhubung).")
        print("\n  Ringkasan klaster (maks 5 terbesar):")
        print("  " + _tampil(ringkas.head(5)).replace("\n", "\n  "))
        print(f"\n  Anggota klaster 1 yang paling terhubung di dalam klaster (maks {args.limit}):")
        print("  " + _tampil(komunitas[komunitas["klaster"] == 1].head(args.limit).drop(columns=["klaster"])).replace("\n", "\n  "))

    banner(f"c) user_paling_terhubung({args.limit}) - degree centrality")
    print(_tampil(user_paling_terhubung(args.limit)[[
        "user_id", "out_degree", "in_degree", "total_degree", "age", "gender", "completed_level_of_education",
        "completion_percentage", "registration", "marital_status"]]))

    banner(f"(bonus) rekomendasi_hobi_sama({user_id}) - hobi sama, belum berteman")
    sehobi = rekomendasi_hobi_sama(user_id, args.limit)
    print(_tampil(sehobi) if len(sehobi) else "  (tidak ada kandidat; user ini mungkin tidak punya hobi)")

    if not args.skip_benchmark:
        banner("d) bandingkan_performa_query() - teman dari teman dari teman (3 hop)")
        _ringkas_benchmark(bandingkan_performa_query(ulangi=args.ulangi, pemanasan=args.pemanasan), args.ulangi)


if __name__ == "__main__":
    main()
