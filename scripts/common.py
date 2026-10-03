"""Helper bersama untuk script 01-04.

Modul ini sengaja dipisah supaya dua hal yang HARUS konsisten antar-database
cuma ditulis sekali:
  * aturan memecah kolom `hobbies` (dipakai 02 untuk SQLite dan 03 untuk Neo4j),
  * cara membuka koneksi Neo4j lokal beserta pesan error yang ramah (03 dan 04).

Import modul ini juga mengatur stdout/stderr ke UTF-8 supaya output tidak
crash di terminal Windows saat di-redirect ke file.
"""
from __future__ import annotations

import logging
import os
import re
import socket
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

try:
    import pandas as pd
    from dotenv import load_dotenv
    from neo4j import Driver, GraphDatabase
    from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable, SessionExpired
except ModuleNotFoundError as _exc:  # biasanya: IDE memakai interpreter yang bukan environment proyek
    raise SystemExit(
        f"[ERROR] Modul Python '{_exc.name}' belum terpasang di interpreter yang sedang dipakai:\n"
        f"        {sys.executable}\n"
        "        Pilih environment 'hybrid-db' sebagai interpreter di IDE Anda (PyCharm: Settings > Project >\n"
        "        Python Interpreter), atau pasang paketnya: pip install -r requirements.txt"
    ) from None

# Notifikasi peringatan dari server Neo4j (mis. perubahan format di versi mayor berikutnya) hanya bising di sini.
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# --------------------------------------------------------------------------
# Lokasi file
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
QUERIES_DIR = PROJECT_ROOT / "queries"

PROFILES_GZ = DATA_DIR / "soc-pokec-profiles.txt.gz"
RELATIONSHIPS_GZ = DATA_DIR / "soc-pokec-relationships.txt.gz"
USERS_CSV = DATA_DIR / "users_sample.csv"
EDGES_CSV = DATA_DIR / "edges_sample.csv"
SQLITE_PATH = DATA_DIR / "pokec.db"

# Kolom bertipe integer di users_sample.csv (boleh kosong -> <NA>).
USER_INT_COLUMNS = ["user_id", "public", "completion_percentage", "gender", "age"]

# Aturan penyaringan hobi (lihat build_hobby_rows).
HOBBY_MIN_USERS = 3
HOBBY_MAX_LEN = 40


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def fail(message: str, code: int = 1) -> None:
    """Cetak pesan error singkat ke stderr lalu keluar (tanpa traceback)."""
    print(f"\n[ERROR] {message}", file=sys.stderr)
    raise SystemExit(code)


def require_file(path: Path, hint: str) -> None:
    if not path.exists():
        fail(f"File tidak ditemukan: {path}\n        {hint}")


def read_query(name: str) -> str:
    """Baca file query dari folder /queries (satu-satunya sumber query)."""
    return (QUERIES_DIR / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# CSV hasil subsampling
# --------------------------------------------------------------------------
def read_users_csv() -> pd.DataFrame:
    """Baca data/users_sample.csv. Sel kosong = data tidak tersedia (NA)."""
    require_file(USERS_CSV, "Jalankan dulu: python scripts/01_subsample_data.py")
    return pd.read_csv(
        USERS_CSV,
        dtype={c: "Int64" for c in USER_INT_COLUMNS},
        keep_default_na=False,
        na_values=[""],
    )


def read_edges_csv() -> pd.DataFrame:
    """Baca data/edges_sample.csv (kolom user_id_1 -> user_id_2, directed)."""
    require_file(EDGES_CSV, "Jalankan dulu: python scripts/01_subsample_data.py")
    return pd.read_csv(EDGES_CSV, dtype="int64")


# --------------------------------------------------------------------------
# Hobi
# --------------------------------------------------------------------------
def normalize_hobby(text: str) -> str:
    """Rapikan satu nama hobi: huruf kecil, spasi ganda dibuang."""
    return " ".join(str(text).lower().split())


def split_hobbies(raw) -> list[str]:
    """Pecah string hobi gabungan ("a, b, c") jadi list unik berurutan.

    Database: tidak ada (murni Python). Dipakai bersama oleh 02 dan 03 agar
    tabel `hobbies` di SQLite dan node `Hobby` di Neo4j identik.
    """
    if raw is None or pd.isna(raw):
        return []
    hobbies: dict[str, None] = {}
    for part in str(raw).split(","):
        hobby = normalize_hobby(part)
        if hobby and hobby != "null" and len(hobby) <= HOBBY_MAX_LEN:
            hobbies[hobby] = None
    return list(hobbies)


def build_hobby_rows(users: pd.DataFrame) -> pd.DataFrame:
    """Ubah kolom `hobbies` (string gabungan) jadi baris (user_id, hobby).

    Database: tidak ada (murni Python). Kolom hobi Pokec berisi ~33 pilihan baku
    ("pocuvanie hudby", "sportovanie", ...) PLUS ratusan ribu teks bebas yang
    hampir semuanya hanya muncul sekali. Hobi yang dimiliki kurang dari
    HOBBY_MIN_USERS user dibuang: hobi yang tak dimiliki orang lain memang
    tidak berguna untuk analisis "hobi yang sama".
    """
    rows = [
        (int(user_id), hobby)
        for user_id, raw in zip(users["user_id"], users["hobbies"])
        for hobby in split_hobbies(raw)
    ]
    hobby_rows = pd.DataFrame(rows, columns=["user_id", "hobby"])
    users_per_hobby = hobby_rows.groupby("hobby")["user_id"].transform("size")
    return hobby_rows[users_per_hobby >= HOBBY_MIN_USERS].reset_index(drop=True)


# --------------------------------------------------------------------------
# SQLite
# --------------------------------------------------------------------------
def connect_sqlite() -> sqlite3.Connection:
    """Buka data/pokec.db (harus sudah dibuat oleh script 02)."""
    require_file(SQLITE_PATH, "Jalankan dulu: python scripts/02_load_sqlite.py")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --------------------------------------------------------------------------
# Neo4j (selalu lokal - Neo4j Desktop, tidak pernah cloud/AuraDB)
# --------------------------------------------------------------------------
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
PLACEHOLDER_PASSWORD = "isi_dengan_password_dbms_anda"


def neo4j_settings() -> tuple[str, str, str]:
    """Baca NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD dari .env dan validasi.

    URI yang host-nya bukan localhost DITOLAK, sehingga AuraDB atau server
    cloud lain tidak mungkin terpakai walaupun .env salah isi.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687").strip()
    user = os.getenv("NEO4J_USER", "neo4j").strip()
    password = os.getenv("NEO4J_PASSWORD", "")

    if not password or password == PLACEHOLDER_PASSWORD:
        fail(
            "NEO4J_PASSWORD belum diisi.\n"
            "        Salin .env.example menjadi .env, lalu isi password DBMS lokal Anda "
            "(yang dibuat di Neo4j Desktop)."
        )
    host = (urlparse(uri).hostname or "").lower()
    if host not in LOCAL_HOSTS:
        fail(
            f"NEO4J_URI='{uri}' ditolak: proyek ini hanya boleh memakai Neo4j Desktop LOKAL "
            "(host localhost / 127.0.0.1), bukan AuraDB atau cloud.\n"
            "        Gunakan NEO4J_URI=bolt://localhost:7687"
        )
    return uri, user, password


def uri_ipv4(uri: str) -> str:
    """Ganti host 'localhost' dengan 127.0.0.1.

    Di Windows, 'localhost' dicoba lewat IPv6 (::1) dulu dan baru ditolak setelah ±2 detik sebelum pindah ke IPv4, sehingga
    SETIAP koneksi baru terasa lambat (terukur: ±2.050 ms vs ±13 ms). Alamatnya tetap komputer ini sendiri.
    """
    return re.sub(r"(?i)//localhost(?=[:/]|$)", "//127.0.0.1", uri, count=1)


def _ipv6_menjawab(uri: str) -> bool:
    """Apakah ada yang mendengarkan di ::1 pada port URI ini? (pengecekan 0,25 detik, supaya gagal tetap cepat)"""
    try:
        with socket.create_connection(("::1", urlparse(uri).port or 7687), timeout=0.25):
            return True
    except OSError:
        return False


def connect_neo4j() -> Driver:
    """Buka koneksi ke Neo4j lokal dan pastikan benar-benar bisa dipakai."""
    uri, user, password = neo4j_settings()
    percobaan = [uri_ipv4(uri)]
    for i, alamat in enumerate(percobaan):   # percobaan kedua (alamat asli) hanya ditambahkan bila IPv4 gagal DAN IPv6 menjawab
        driver = None
        try:
            driver = GraphDatabase.driver(alamat, auth=(user, password))
            driver.verify_connectivity()
            return driver
        except AuthError:
            fail(
                f"Login ke Neo4j ({uri}) ditolak: NEO4J_USER / NEO4J_PASSWORD di .env tidak cocok "
                "dengan password DBMS di Neo4j Desktop."
            )
        except (ServiceUnavailable, OSError):
            if driver is not None:
                driver.close()
            if i == 0 and percobaan[0] != uri and _ipv6_menjawab(uri):
                percobaan.append(uri)   # cadangan untuk Neo4j yang ternyata hanya mendengarkan di IPv6 (jarang)
                continue
            fail(
                f"Tidak bisa terhubung ke Neo4j di {uri}.\n"
                "        Pastikan Neo4j Desktop sudah di-Start (DBMS berstatus 'Running'), lalu coba lagi.\n"
                "        Kalau port DBMS Anda bukan 7687, sesuaikan NEO4J_URI di .env."
            )
        except Exception as exc:  # URI/skema tidak valid, versi server tak didukung, dll.
            fail(f"Gagal membuka koneksi Neo4j ({uri}): {exc}")


@contextmanager
def friendly_neo4j_errors():
    """Ubah error Neo4j yang umum (koneksi putus, query ditolak) jadi pesan jelas."""
    try:
        yield
    except (ServiceUnavailable, SessionExpired):
        fail("Koneksi ke Neo4j terputus. Pastikan Neo4j Desktop masih berstatus 'Running'.")
    except Neo4jError as exc:
        fail(f"Neo4j menolak perintah [{exc.code}]: {exc.message}")
