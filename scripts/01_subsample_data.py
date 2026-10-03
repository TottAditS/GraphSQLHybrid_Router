"""Langkah 1 - Download dan subsampling dataset Pokec (SNAP Stanford).

Dataset penuh (1,6 juta user, 30,6 juta edge) terlalu besar untuk eksperimen di
laptop, jadi script ini mengambil SATU region saja lalu menyimpan induced
subgraph-nya ke CSV. Langkah-langkahnya:

  1. Unduh dua file .gz ke data/ (dilewati kalau sudah ada).
  2. Hitung jumlah user per region -> kandidat = region berukuran 3.000-8.000 user.
  3. Satu kali baca file edge: hitung berapa edge yang kedua ujungnya sama-sama
     di region kandidat. Region terpilih = yang paling rapat (rata-rata teman
     sesama region terbanyak), supaya traversal multi-hop nanti bermakna.
  4. Ambil profil lengkap user region itu + HANYA edge yang kedua ujungnya ada
     di dalamnya (induced subgraph), bersihkan, simpan ke CSV.

Output : data/users_sample.csv dan data/edges_sample.csv
Database: belum ada (hanya file mentah -> CSV perantara). Dengan CSV ini, script
          02/03/04 tidak perlu lagi menyentuh file asli yang besar.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import gzip
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    DATA_DIR,
    EDGES_CSV,
    PROFILES_GZ,
    RELATIONSHIPS_GZ,
    USERS_CSV,
    banner,
    build_hobby_rows,
    fail,
)

SNAP_BASE_URL = "https://snap.stanford.edu/data"

# Posisi kolom (0-based) di soc-pokec-profiles.txt menurut soc-pokec-readme.txt.
# File aslinya punya 60 field per baris: field ke-60 selalu kosong (ada tab di
# ujung tiap baris), jadi cukup kolom di bawah yang dipakai.
PROFILE_COL = {
    "user_id": 0,
    "public": 1,
    "completion_percentage": 2,
    "gender": 3,
    "region": 4,
    "last_login": 5,
    "registration": 6,
    "age": 7,
    "hobbies": 11,
    "body_type": 14,
    "eye_color": 16,
    "hair_color": 17,
    "hair_type": 18,
    "completed_level_of_education": 19,
    "favourite_color": 20,
    "relation_to_smoking": 21,
    "relation_to_alcohol": 22,
    "sign_in_zodiac": 23,
    "marital_status": 28,
}
# Urutan kolom di users_sample.csv (18 kolom untuk tabel `users` + `hobbies`
# mentah yang nanti dipecah jadi tabel `hobbies` / node `Hobby`).
OUTPUT_COLUMNS = [c for c in PROFILE_COL if c != "hobbies"] + ["hobbies"]
TEXT_COLUMNS = [
    "body_type", "eye_color", "hair_color", "hair_type", "completed_level_of_education",
    "favourite_color", "relation_to_smoking", "relation_to_alcohol", "marital_status",
    "sign_in_zodiac", "hobbies",
]
# Umur di luar rentang ini (dan 0 = "tidak diisi") dianggap tidak valid -> NULL.
AGE_MIN, AGE_MAX = 10, 90


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------
def download(url: str, dest: Path) -> None:
    """Unduh url ke dest lewat file .part, baru di-rename kalau ukurannya lengkap."""
    part = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "pokec-hybrid-experiment"})
    with urllib.request.urlopen(request, timeout=60) as response, open(part, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done, next_mark = 0, 10
        while block := response.read(1024 * 1024):
            out.write(block)
            done += len(block)
            if total and done * 100 // total >= next_mark:
                print(f"      {done / 1e6:7.1f} / {total / 1e6:.1f} MB ({next_mark}%)", flush=True)
                next_mark += 10
    if total and done != total:
        part.unlink(missing_ok=True)
        raise OSError(f"ukuran tidak lengkap ({done} dari {total} byte)")
    part.replace(dest)


def ensure_dataset() -> None:
    """Pastikan kedua file .gz ada di data/; unduh otomatis kalau belum."""
    DATA_DIR.mkdir(exist_ok=True)
    for path in (PROFILES_GZ, RELATIONSHIPS_GZ):
        if path.exists():
            print(f"  {path.name}: sudah ada ({path.stat().st_size / 1e6:.0f} MB), unduhan dilewati")
            continue
        url = f"{SNAP_BASE_URL}/{path.name}"
        print(f"  {path.name}: mengunduh dari {url}")
        try:
            download(url, path)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            fail(
                f"Gagal mengunduh {path.name} ({exc}).\n"
                "        Unduh manual: buka https://snap.stanford.edu/data/soc-Pokec.html, simpan\n"
                "        soc-pokec-profiles.txt.gz dan soc-pokec-relationships.txt.gz ke folder data/,\n"
                "        lalu jalankan ulang script ini."
            )


# --------------------------------------------------------------------------
# Membaca file mentah
# --------------------------------------------------------------------------
def read_profiles(columns: list[str], dtype: dict | None = None, chunksize: int | None = None):
    """Baca kolom terpilih dari soc-pokec-profiles.txt.gz.

    quoting=NONE wajib: ±450 ribu baris mengandung tanda kutip " di teks bebas,
    dan parser CSV biasa akan salah menggabungkan baris. na_filter=False supaya
    string "null" tetap apa adanya (kita tangani sendiri di clean_users).
    """
    index_to_name = {PROFILE_COL[c]: c for c in columns}
    frame_or_chunks = pd.read_csv(
        PROFILES_GZ,
        sep="\t",
        header=None,
        usecols=sorted(index_to_name),
        dtype={PROFILE_COL[c]: t for c, t in (dtype or {}).items()},
        quoting=csv.QUOTE_NONE,
        na_filter=False,
        encoding="utf-8",
        chunksize=chunksize,
    )
    if chunksize is None:
        return frame_or_chunks.rename(columns=index_to_name)
    return (chunk.rename(columns=index_to_name) for chunk in frame_or_chunks)


def pick_region(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    """Langkah 2-3: hitung user per region, lalu pilih region lewat satu kali baca edge.

    Return: (kandidat, user_eligible, edge_intra_region, region_per_kode)
    """
    t0 = time.time()
    print("\n[2/5] Membaca user_id, completion_percentage, region dari semua profil ...")
    all_users = read_profiles(
        ["user_id", "completion_percentage", "region"],
        dtype={"user_id": "int32", "completion_percentage": "int16", "region": "category"},
    )
    eligible = all_users[
        (all_users["region"] != "null") & (all_users["completion_percentage"] >= args.min_completion)
    ]
    sizes = eligible["region"].value_counts()
    sizes = sizes[sizes > 0]
    print(
        f"      {len(all_users):,} profil dibaca ({time.time() - t0:.0f} dtk); {len(sizes)} region; "
        f"{int(sizes.between(args.min_users, args.max_users).sum())} region berukuran "
        f"{args.min_users:,}-{args.max_users:,} user"
    )

    if args.region:
        wanted = args.region.strip().lower()
        if wanted not in sizes.index:
            hints = difflib.get_close_matches(wanted, [str(r) for r in sizes.index], n=5, cutoff=0.4)
            fail(f"Region '{args.region}' tidak ada di dataset. Mirip: {hints or '(tidak ada)'}")
        candidates = [wanted]
    else:
        candidates = [str(r) for r in sizes[sizes.between(args.min_users, args.max_users)].index]
        if not candidates:
            fail("Tidak ada region dengan jumlah user di rentang itu. Longgarkan --min-users / --max-users.")

    # code_of[user_id] = indeks region kandidat (atau -1). Dipakai untuk menyaring edge secara vektor.
    region_codes = eligible["region"].cat.set_categories(candidates).cat.codes
    code_of = np.full(int(all_users["user_id"].max()) + 1, -1, dtype=np.int32)
    code_of[eligible["user_id"].to_numpy()] = region_codes.to_numpy()

    t0 = time.time()
    print(f"\n[3/5] Membaca ±30,6 juta edge, menyaring edge di dalam {len(candidates)} region kandidat ...")
    src_parts, dst_parts, code_parts = [], [], []
    total_edges = self_loops = 0
    reader = pd.read_csv(
        RELATIONSHIPS_GZ, sep="\t", header=None, names=["a", "b"], dtype=np.int32, chunksize=2_000_000
    )
    for chunk in reader:
        a, b = chunk["a"].to_numpy(), chunk["b"].to_numpy()
        total_edges += len(a)
        self_loops += int((a == b).sum())
        in_range = (a < len(code_of)) & (b < len(code_of))
        a, b = a[in_range], b[in_range]
        code_a, code_b = code_of[a], code_of[b]
        keep = (code_a >= 0) & (code_a == code_b) & (a != b)
        src_parts.append(a[keep])
        dst_parts.append(b[keep])
        code_parts.append(code_a[keep])
    src, dst, code = (np.concatenate(p) for p in (src_parts, dst_parts, code_parts))
    print(
        f"      {total_edges:,} edge dibaca ({time.time() - t0:.0f} dtk); "
        f"{self_loops} self-loop dibuang; {len(src):,} edge jatuh di dalam region kandidat"
    )

    table = pd.DataFrame({"region": candidates})
    table["users"] = [int((sizes.get(r, 0))) for r in candidates]
    table["edges"] = np.bincount(code, minlength=len(candidates))
    table["avg_friends"] = table["edges"] / table["users"]
    table = table.sort_values(["avg_friends", "users"], ascending=False).reset_index(drop=True)

    edges = pd.DataFrame({"user_id_1": src, "user_id_2": dst, "code": code})
    return table, eligible, edges, pd.Series(candidates)


# --------------------------------------------------------------------------
# Pembersihan
# --------------------------------------------------------------------------
def clean_users(raw: pd.DataFrame) -> pd.DataFrame:
    """Rapikan profil mentah: "null" -> NULL, umur tak valid -> NULL, teks diseragamkan.

    Database: tidak ada. Hasilnya langsung jadi users_sample.csv.
    """
    df = raw[OUTPUT_COLUMNS].copy()
    for column in df.columns:
        if column != "user_id":
            df[column] = df[column].mask(df[column] == "null")

    for column in TEXT_COLUMNS:  # huruf kecil + spasi ganda dibuang
        text = df[column].str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
        df[column] = text.mask(text == "")
    for column in ("last_login", "registration"):  # "2012-05-25 11:20:00.0" -> tanpa ".0"
        df[column] = df[column].str.replace(r"\.0$", "", regex=True)

    for column in ("public", "completion_percentage", "gender", "age"):
        df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")
    df["public"] = df["public"].where(df["public"].isin([0, 1]))
    df["gender"] = df["gender"].where(df["gender"].isin([0, 1]))  # 1 = pria, 0 = wanita
    df["age"] = df["age"].where(df["age"].between(AGE_MIN, AGE_MAX).fillna(False))  # 0 = tidak diisi (README)
    return df.sort_values("user_id").reset_index(drop=True)


# --------------------------------------------------------------------------
# Ringkasan
# --------------------------------------------------------------------------
def print_summary(users: pd.DataFrame, edges: pd.DataFrame, table: pd.DataFrame, chosen: str) -> None:
    n_users, n_edges = len(users), len(edges)
    banner("RINGKASAN HASIL SAMPLING")
    print(f"Region terpilih      : {chosen}")
    print(f"Jumlah user          : {n_users:,}")
    print(f"Jumlah edge (FRIEND) : {n_edges:,}   (directed, induced subgraph)")
    print(f"Rata-rata teman/user : {n_edges / n_users:.1f} (out-degree)")

    out_deg = edges["user_id_1"].value_counts().reindex(users["user_id"], fill_value=0)
    in_deg = edges["user_id_2"].value_counts().reindex(users["user_id"], fill_value=0)
    isolated = int(((out_deg.to_numpy() == 0) & (in_deg.to_numpy() == 0)).sum())
    key = edges["user_id_1"].to_numpy(dtype=np.int64) * 10_000_000 + edges["user_id_2"].to_numpy(dtype=np.int64)
    reverse = edges["user_id_2"].to_numpy(dtype=np.int64) * 10_000_000 + edges["user_id_1"].to_numpy(dtype=np.int64)
    print(f"Out-degree           : min {out_deg.min()} | median {int(out_deg.median())} | maks {out_deg.max()}")
    print(f"User tanpa koneksi   : {isolated:,} ({isolated / n_users:.1%})")
    print(f"Edge timbal-balik    : {np.isin(reverse, key).mean():.1%} (A->B yang juga punya B->A)")

    banner("Distribusi gender (1 = pria, 0 = wanita)")
    gender = users["gender"].value_counts(dropna=False)
    for value, count in gender.items():
        label = {1: "pria", 0: "wanita"}.get(value, "tidak diisi")
        print(f"  {label:<11}: {count:,} ({count / n_users:.1%})")

    banner("Distribusi region")
    for value, count in users["region"].value_counts().items():
        print(f"  {value}: {count:,} user (100%; sampling memang per satu region)")
    print("  Kandidat lain yang dibandingkan (10 teratas menurut rata-rata teman sesama region):")
    shown = table.head(10).copy()
    shown["avg_friends"] = shown["avg_friends"].round(2)
    shown.insert(0, "dipilih", ["*" if r == chosen else "" for r in shown["region"]])
    print("    " + shown.to_string(index=False).replace("\n", "\n    "))

    banner("Umur dan kelengkapan profil")
    age = users["age"].dropna().astype(int)
    print(f"  Umur terisi/valid ({AGE_MIN}-{AGE_MAX}): {len(age):,} ({len(age) / n_users:.1%}) | "
          f"min {age.min()} | median {int(age.median())} | maks {age.max()}")
    completion = users["completion_percentage"].astype(int)
    print(f"  completion_percentage      : min {completion.min()} | median {int(completion.median())} | maks {completion.max()}")
    filled = (users.notna().mean() * 100).round(0).astype(int)
    print("  Persentase terisi per kolom: " + ", ".join(f"{c}={v}%" for c, v in filled.items() if c != "user_id"))

    hobby_rows = build_hobby_rows(users)
    banner("Hobi (setelah dipecah dan disaring)")
    print(f"  {hobby_rows['user_id'].nunique():,} user punya hobi ({hobby_rows['user_id'].nunique() / n_users:.1%}); "
          f"{hobby_rows['hobby'].nunique()} hobi berbeda; {len(hobby_rows):,} pasangan user-hobi")
    print("  10 hobi terbanyak: " + ", ".join(f"{h} ({c})" for h, c in hobby_rows["hobby"].value_counts().head(10).items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Download + subsampling dataset Pokec ke CSV.")
    parser.add_argument("--region", help="paksa pakai region tertentu, mis. 'zilinsky kraj, zilina'")
    parser.add_argument("--min-users", type=int, default=3000, help="batas bawah ukuran region kandidat")
    parser.add_argument("--max-users", type=int, default=8000, help="batas atas ukuran region kandidat")
    parser.add_argument("--min-completion", type=int, default=0,
                        help="filter kualitas: hanya user dengan completion_percentage >= nilai ini (default 0 = semua)")
    args = parser.parse_args()

    banner("[1/5] Memeriksa dataset di data/")
    ensure_dataset()

    try:
        table, eligible, edges, candidates = pick_region(args)
        chosen = str(table.loc[0, "region"])  # tabel sudah terurut; dengan --region isinya satu baris
        chosen_code = list(candidates).index(chosen)

        print(f"\n[4/5] Region terpilih: {chosen}")
        user_ids = eligible.loc[eligible["region"] == chosen, "user_id"].to_numpy()
        edges = (
            edges[edges["code"] == chosen_code][["user_id_1", "user_id_2"]]
            .drop_duplicates()
            .sort_values(["user_id_1", "user_id_2"])
            .reset_index(drop=True)
            .astype("int64")
        )

        print("\n[5/5] Mengambil profil lengkap user terpilih + menulis CSV ...")
        wanted = set(user_ids.tolist())
        # Semua kolom dibaca sebagai teks (kecuali user_id) agar tipe tidak berubah-ubah antar chunk.
        dtypes = {c: "str" for c in OUTPUT_COLUMNS} | {"user_id": "int32"}
        chunks = read_profiles(OUTPUT_COLUMNS, dtype=dtypes, chunksize=200_000)
        raw = pd.concat([c[c["user_id"].isin(wanted)] for c in chunks], ignore_index=True)
    except (EOFError, gzip.BadGzipFile, zlib.error) as exc:
        fail(f"File .gz rusak atau tidak lengkap ({exc}). Hapus file di data/ lalu jalankan ulang untuk mengunduh ulang.")

    users = clean_users(raw)
    users.to_csv(USERS_CSV, index=False, encoding="utf-8", lineterminator="\n")
    edges.to_csv(EDGES_CSV, index=False, encoding="utf-8", lineterminator="\n")
    print(f"      ditulis: {USERS_CSV.relative_to(USERS_CSV.parents[1])} ({len(users):,} baris), "
          f"{EDGES_CSV.relative_to(EDGES_CSV.parents[1])} ({len(edges):,} baris)")

    print_summary(users, edges, table, chosen)


if __name__ == "__main__":
    main()
