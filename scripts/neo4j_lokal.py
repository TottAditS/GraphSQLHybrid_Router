"""Menyalakan, memeriksa, dan mematikan Neo4j lokal dari NOTEBOOK.

Dipakai HANYA oleh kedua notebook di folder notebooks/, atas permintaan eksplisit pengguna. Script 01-04 sengaja tidak memakai
modul ini: mereka tidak pernah menjalankan Neo4j sendiri. Semua koneksi tetap hanya ke localhost.

Yang dinyalakan adalah Neo4j Community hasil ekstrak zip (folder diisi di .env sebagai NEO4J_HOME). Kalau Anda memakai
Neo4j Desktop, nyalakan lewat tombol Start di Desktop dan abaikan fungsi nyalakan()/matikan().
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError

from common import EDGES_CSV, LOCAL_HOSTS, PLACEHOLDER_PASSWORD, PROJECT_ROOT, SQLITE_PATH, USERS_CSV, uri_ipv4

_proses_terakhir = None   # simpan referensi Popen supaya tidak di-garbage-collect


# --------------------------------------------------------------------------
# Konfigurasi
# --------------------------------------------------------------------------
def _konfig() -> dict[str, str]:
    """Isi .env, ditimpa variabel lingkungan NEO4J_* yang sudah ada (urutan yang sama dengan python-dotenv)."""
    nilai = {k: v for k, v in dotenv_values(PROJECT_ROOT / ".env").items() if v is not None}
    nilai.update({k: v for k, v in os.environ.items() if k.startswith("NEO4J_")})
    return nilai


def _alamat(konfig: dict[str, str]) -> tuple[str, int]:
    url = urlparse(konfig.get("NEO4J_URI", "bolt://localhost:7687"))
    return (url.hostname or "localhost").lower(), url.port or 7687


def _home(konfig: dict[str, str]) -> Path | None:
    teks = konfig.get("NEO4J_HOME", "").strip()
    return Path(teks) if teks and (Path(teks) / "bin").is_dir() else None


def bolt_terbuka() -> bool:
    """Apakah ada yang mendengarkan di port Bolt (default 7687) pada komputer ini?"""
    _, port = _alamat(_konfig())
    # 127.0.0.1 dulu (cepat); 'localhost' di Windows dicoba lewat IPv6 yang ditolak setelah ±2 detik. ::1 hanya cadangan singkat.
    for alamat, batas in (("127.0.0.1", 1), ("::1", 0.25)):
        try:
            with socket.create_connection((alamat, port), timeout=batas):
                return True
        except OSError:
            continue
    return False


def _tail_log(log: Path, n: int = 15) -> str:
    try:
        return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return "(log tidak bisa dibaca)"


# --------------------------------------------------------------------------
# Nyalakan / matikan
# --------------------------------------------------------------------------
def nyalakan(tunggu: int = 120) -> bool:
    """Nyalakan Neo4j lokal di latar belakang (tanpa jendela) dan tunggu sampai siap menerima koneksi.

    Setara dengan pintasan Desktop "Mulai Neo4j (lokal)". Prosesnya terpisah dari proses Python ini (bertahan kalau yang
    menyalakan skrip Python biasa), tetapi di dalam kernel Jupyter ia ikut berhenti saat kernel dimatikan (teramati lewat
    nbconvert). Matikan dengan matikan(). Keluaran Neo4j disimpan di <NEO4J_HOME>/logs/notebook-console.log.
    Mengembalikan True jika sudah siap.
    """
    global _proses_terakhir
    port = _alamat(_konfig())[1]
    if bolt_terbuka():
        print(f"[OK] Neo4j sudah menyala di port {port}. Tidak perlu dinyalakan lagi.")
        return True
    home = _home(_konfig())
    if home is None:
        print("[BELUM] NEO4J_HOME belum diisi (atau foldernya tidak punya subfolder 'bin') di file .env.\n"
              "        Isi dengan folder Neo4j Community Anda, mis. NEO4J_HOME=D:\\Softwares\\neo4j-community-5.26.31,\n"
              "        atau nyalakan Neo4j sendiri (pintasan 'Mulai Neo4j (lokal)' / tombol Start di Neo4j Desktop).")
        return False

    log = home / "logs" / "notebook-console.log"
    log.parent.mkdir(exist_ok=True)
    if os.name == "nt":
        perintah = ["cmd.exe", "/c", str(home / "bin" / "neo4j.bat"), "console"]
        opsi = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        perintah = [str(home / "bin" / "neo4j"), "console"]
        opsi = {"start_new_session": True}
    print(f"Menyalakan Neo4j dari {home} ... (hanya bisa diakses dari komputer ini)")
    with open(log, "wb") as keluaran:
        _proses_terakhir = subprocess.Popen(perintah, cwd=home, stdin=subprocess.DEVNULL, stdout=keluaran,
                                            stderr=subprocess.STDOUT, **opsi)
    mulai = time.time()
    while time.time() - mulai < tunggu:
        if bolt_terbuka():
            print(f"[OK] Neo4j siap dalam {time.time() - mulai:.0f} detik (port {port}). Browser interaktif: http://localhost:7474")
            return True
        if _proses_terakhir.poll() is not None:
            break
        time.sleep(1)
    print("[GAGAL] Neo4j tidak menjadi siap. Penyebab umum: Java 17 belum ada di PATH, atau port sudah dipakai program lain.\n"
          f"        {log.name} (baris terakhir):\n" + _tail_log(log))
    return False


def matikan() -> None:
    """Hentikan proses Neo4j dari folder NEO4J_HOME (baik yang dinyalakan dari notebook maupun lewat pintasan).

    Mode console tidak punya cara berhenti yang lebih halus dari luar, jadi prosesnya dihentikan paksa. Neo4j memulihkan
    diri otomatis saat dinyalakan lagi; kalau datanya sampai bermasalah, jalankan scripts/03_sync_to_neo4j.py --reset.
    """
    if os.name != "nt":
        print("matikan() hanya mendukung Windows; hentikan Neo4j dengan Ctrl+C di terminal tempat ia berjalan.")
        return
    home = _home(_konfig())
    if home is None:
        print("[BELUM] NEO4J_HOME belum diisi di .env, jadi tidak tahu proses mana yang harus dimatikan.")
        return
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" | "
          "Where-Object { $_.CommandLine -like '*" + str(home).replace("'", "''") + "*' } | ForEach-Object { $_.ProcessId }")
    hasil = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=60)
    pids = [int(x) for x in hasil.stdout.split() if x.isdigit()]
    if not pids:
        print("Tidak ada proses Neo4j dari folder itu yang sedang berjalan.")
        return
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    mulai = time.time()
    while time.time() - mulai < 20 and bolt_terbuka():
        time.sleep(1)
    print("[OK] Neo4j dimatikan." if not bolt_terbuka() else "[GAGAL] Port masih terbuka; matikan manual lewat Task Manager (java.exe).")


# --------------------------------------------------------------------------
# Pemeriksaan dan bantuan alur notebook
# --------------------------------------------------------------------------
def jumlah_user() -> int | None:
    """Jumlah node User di graf, atau None kalau tidak bisa terhubung/login. Hanya mau ke localhost."""
    konfig = _konfig()
    host, port = _alamat(konfig)
    if host not in LOCAL_HOSTS or not konfig.get("NEO4J_PASSWORD") or not bolt_terbuka():
        return None
    try:
        driver = GraphDatabase.driver(uri_ipv4(konfig.get("NEO4J_URI", "bolt://localhost:7687")),
                                      auth=(konfig.get("NEO4J_USER", "neo4j"), konfig["NEO4J_PASSWORD"]))
        try:
            with driver.session() as sesi:
                return int(sesi.run("MATCH (u:User) RETURN count(u) AS n").single()["n"])
        finally:
            driver.close()
    except AuthError:
        return -1
    except Exception:
        return None


def baca(query: str, **parameter) -> list[dict]:
    """Jalankan satu query baca ke Neo4j lokal dan kembalikan list of dict. Menolak alamat selain localhost."""
    konfig = _konfig()
    if _alamat(konfig)[0] not in LOCAL_HOSTS:
        raise ValueError("NEO4J_URI harus mengarah ke localhost.")
    driver = GraphDatabase.driver(uri_ipv4(konfig.get("NEO4J_URI", "bolt://localhost:7687")),
                                  auth=(konfig.get("NEO4J_USER", "neo4j"), konfig.get("NEO4J_PASSWORD", "")))
    try:
        with driver.session() as sesi:
            return [rekaman.data() for rekaman in sesi.run(query, **parameter)]
    finally:
        driver.close()


def cek_kesiapan() -> dict:
    """Periksa semua prasyarat notebook dan cetak apa yang masih kurang beserta langkah berikutnya.

    Mengembalikan {"wajib_ok": bool, "menyala": bool, "jumlah_user": int | None}; wajib_ok = password, alamat lokal,
    CSV, dan SQLite sudah siap (Neo4j menyala dan graf terisi diurus langkah-langkah berikutnya).
    """
    konfig = _konfig()
    host, _ = _alamat(konfig)
    baris = []

    def tambah(ok: bool | None, nama: str, ket: str) -> None:
        baris.append((ok, nama, ket))

    tambah(True, "Interpreter / kernel", sys.executable + ("" if "hybrid-db" in sys.executable.lower()
                                                           else "  (bukan env 'hybrid-db'; tak masalah selama paket terpasang)"))
    password = konfig.get("NEO4J_PASSWORD", "")
    kredensial_ok = bool(password) and password != PLACEHOLDER_PASSWORD
    tambah(kredensial_ok, "Password Neo4j di .env",
           "terisi" if kredensial_ok else "salin .env.example menjadi .env, lalu isi NEO4J_PASSWORD")
    tambah(host in LOCAL_HOSTS, "NEO4J_URI mengarah ke localhost",
           f"host = {host}" if host in LOCAL_HOSTS else "harus localhost/127.0.0.1 (cloud sengaja ditolak)")
    csv_ok = USERS_CSV.exists() and EDGES_CSV.exists()
    tambah(csv_ok, "CSV sampel (script 01)", "ada" if csv_ok else "jalankan scripts/01_subsample_data.py")
    tambah(SQLITE_PATH.exists(), "Database SQLite (script 02)",
           "ada" if SQLITE_PATH.exists() else "jalankan scripts/02_load_sqlite.py")
    home = _home(konfig)
    tambah(True if home else None, "NEO4J_HOME (untuk tombol nyalakan)",
           str(home) if home else "tidak diisi: nyalakan Neo4j sendiri (pintasan / Neo4j Desktop)")
    menyala = bolt_terbuka()
    tambah(menyala, "Neo4j sedang menyala",
           "ya" if menyala else "belum menyala (akan dinyalakan di langkah berikutnya)")
    n = jumlah_user() if menyala else None
    if menyala:
        if n == -1:
            tambah(False, "Login dan isi graf", "login ditolak: password di .env tidak cocok dengan password Neo4j")
        elif n is None:
            tambah(False, "Login dan isi graf", "tidak bisa membaca graf")
        elif n == 0:
            tambah(False, "Login dan isi graf", "login OK tetapi graf masih kosong (akan diisi dari CSV di langkah berikutnya)")
        else:
            tambah(True, "Login dan isi graf", f"login OK, {n:,} node User")

    tanda = {True: "[OK]    ", False: "[BELUM] ", None: "[OPSI]  "}
    for ok, nama, ket in baris:
        print(f"{tanda[ok]}{nama:<36} {ket}")

    wajib = [ok for ok, nama, _ in baris if nama in ("Password Neo4j di .env", "NEO4J_URI mengarah ke localhost",
                                                    "CSV sampel (script 01)", "Database SQLite (script 02)")]
    if not all(wajib):
        langkah = "Perbaiki dulu butir [BELUM] di atas, lalu jalankan sel ini lagi."
    elif not menyala:
        langkah = "Lanjut: Neo4j belum menyala; dinyalakan di langkah berikutnya."
    elif n == -1:
        langkah = "Perbaiki NEO4J_PASSWORD di .env (harus sama dengan password DBMS), lalu jalankan sel ini lagi."
    elif not n:
        langkah = "Lanjut: graf masih kosong; diisi dari CSV di langkah berikutnya."
    else:
        langkah = "Semua siap."
    print("\n>>> " + langkah)
    return {"wajib_ok": all(wajib), "menyala": menyala, "jumlah_user": n}


def jalankan_script(nama: str, *argumen: str, sembunyikan_progres: bool = True) -> int:
    """Jalankan scripts/<nama> dengan interpreter yang sama dan tampilkan keluarannya di sel notebook.

    Baris progres per-batch (script 03) disembunyikan secara default supaya keluarannya ringkas.
    """
    proses = subprocess.Popen([sys.executable, "-u", str(PROJECT_ROOT / "scripts" / nama), *argumen], cwd=PROJECT_ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    disembunyikan = 0
    for baris in proses.stdout:
        if sembunyikan_progres and "] batch " in baris:
            disembunyikan += 1
            continue
        print(baris, end="")
    kode = proses.wait()
    if disembunyikan:
        print(f"({disembunyikan} baris progres per-batch disembunyikan)")
    return kode
