"""Alat bantu untuk notebooks/1_tes_semua.ipynb.

Dua hal:
  * Referensi: menghitung ulang jawaban tiap fungsi dengan Python murni langsung dari CSV (tanpa Neo4j, tanpa SQLite, tanpa
    Cypher), sebagai pembanding independen. Kalau jawaban Neo4j/SQLite sama dengan hitungan ini, kodenya benar.
  * CatatanTes: menjalankan tes satu per satu, mengukur waktu fungsi yang diuji, dan mencatat LULUS / GAGAL. Error di satu tes
    dicatat sebagai GAGAL, tidak menghentikan notebook (supaya Run All selalu sampai ke langkah mematikan Neo4j).

Hanya dipakai oleh notebook; script 01-04 tidak bergantung padanya.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from contextlib import contextmanager

import pandas as pd

from common import build_hobby_rows, read_edges_csv, read_users_csv


class Referensi:
    """Jawaban 'kunci' yang dihitung dari CSV dengan Python murni."""

    def __init__(self) -> None:
        self.users = read_users_csv()
        edges = read_edges_csv()
        self.keluar: dict[int, set[int]] = defaultdict(set)
        self.masuk: dict[int, set[int]] = defaultdict(set)
        for a, b in zip(edges["user_id_1"].tolist(), edges["user_id_2"].tolist()):
            self.keluar[a].add(b)
            self.masuk[b].add(a)
        hobi = build_hobby_rows(self.users)
        self.hobi_user = {int(u): set(h) for u, h in hobi.groupby("user_id")["hobby"]}
        self.pemilik = {h: {int(x) for x in u} for h, u in hobi.groupby("hobby")["user_id"]}
        self.jumlah = {"User": len(self.users), "Hobby": hobi["hobby"].nunique(),
                       "FRIEND": len(edges), "HAS_HOBBY": len(hobi)}

    def cocok_profil(self, frame: pd.DataFrame) -> tuple[bool, str]:
        """Tes inti hybrid: kolom profil yang datang dari SQLite sama dengan CSV untuk SETIAP user_id yang dikembalikan Neo4j.

        Memeriksa juga bahwa penggabungan tidak menghilangkan atau menggandakan baris (user_id harus unik) dan bahwa nilai kosong
        (NULL) di SQLite memang kosong di CSV, bukan hilang karena gabungan yang gagal.
        """
        kolom = [k for k in ("age", "gender", "region", "completed_level_of_education") if k in frame.columns]
        profil = self.users.set_index("user_id")
        salah = []
        for baris in frame[["user_id", *kolom]].itertuples(index=False):
            uid = int(baris[0])
            if uid not in profil.index:
                salah.append(f"user {uid} tidak ada di CSV")
                continue
            for nama, nilai in zip(kolom, baris[1:]):
                benar = profil.at[uid, nama]
                kosong_a, kosong_b = pd.isna(nilai), pd.isna(benar)
                if kosong_a != kosong_b or (not kosong_a and nilai != benar):
                    salah.append(f"user {uid}.{nama}: {nilai!r} != {benar!r}")
        unik = bool(frame["user_id"].is_unique)
        if not unik:
            salah.append("user_id ganda setelah digabung")
        ket = f"{len(frame)} baris x {len(kolom)} kolom profil dicocokkan" + (f"; {len(salah)} beda, mis. {salah[0]}" if salah else "")
        return not salah, ket

    def rekomendasi_teman(self, me: int, limit: int = 10) -> list[tuple[int, int]]:
        """Teman dari teman yang belum terhubung (arah mana pun), terurut teman bersama lalu user_id."""
        hitung: Counter = Counter()
        for f in self.keluar[me]:
            for c in self.keluar[f]:
                if c != me and c not in self.keluar[me] and me not in self.keluar[c]:
                    hitung[c] += 1
        return sorted(hitung.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]

    def hobi_sama(self, me: int, limit: int = 10) -> list[tuple[int, int]]:
        punya = self.hobi_user.get(me, set())
        hitung = {}
        for lain, hobi in self.hobi_user.items():
            if lain != me and lain not in self.keluar[me] and me not in self.keluar[lain]:
                k = len(punya & hobi)
                if k:
                    hitung[lain] = k
        return sorted(hitung.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]

    def ukuran_klaster(self, hobi: str, min_size: int = 3) -> list[int]:
        """Ukuran klaster (komponen terhubung, arah diabaikan) pemilik hobi, terbesar dulu."""
        anggota = self.pemilik.get(hobi, set())
        tetangga: dict[int, set[int]] = defaultdict(set)
        for a in anggota:
            for b in self.keluar[a]:
                if b in anggota:
                    tetangga[a].add(b)
                    tetangga[b].add(a)
        terlihat, ukuran = set(), []
        for mulai in anggota:
            if mulai in terlihat:
                continue
            tumpukan, besar = [mulai], 0
            terlihat.add(mulai)
            while tumpukan:
                x = tumpukan.pop()
                besar += 1
                for y in tetangga[x]:
                    if y not in terlihat:
                        terlihat.add(y)
                        tumpukan.append(y)
            if besar >= min_size:
                ukuran.append(besar)
        return sorted(ukuran, reverse=True)

    def derajat_teratas(self, limit: int = 10) -> list[tuple[int, int]]:
        """[(total_degree, user_id)] terbesar dulu; seri diurutkan user_id."""
        semua = ((len(self.keluar[u]) + len(self.masuk[u]), u) for u in self.users["user_id"].tolist())
        return sorted(semua, key=lambda t: (-t[0], t[1]))[:limit]

    def tiga_hop(self, a: int) -> tuple[int, int]:
        """(jumlah path 3-relasi, jumlah user unik di ujungnya); satu relasi tidak dipakai dua kali, ujung != a."""
        unik, path = set(), 0
        for b in self.keluar[a]:
            for c in self.keluar[b]:
                if (b, c) == (a, b):
                    continue
                for d in self.keluar[c]:
                    if (c, d) == (a, b) or (c, d) == (b, c) or d == a:
                        continue
                    path += 1
                    unik.add(d)
        return path, len(unik)


def ukur(fungsi) -> tuple[object, float]:
    """Jalankan fungsi, kembalikan (hasil, waktu dalam milidetik)."""
    mulai = time.perf_counter()
    hasil = fungsi()
    return hasil, (time.perf_counter() - mulai) * 1000


class CatatanTes:
    """Menjalankan tes dan mencatat hasilnya (LULUS / GAGAL), waktu, dan keterangan."""

    def __init__(self) -> None:
        self.baris: list[dict] = []
        self.kelompok = ""

    def catat(self, nama: str, lulus: bool, keterangan: str = "", waktu_ms: float | None = None) -> None:
        self.baris.append({"kelompok": self.kelompok, "tes": nama, "hasil": "LULUS" if lulus else "GAGAL",
                           "waktu_ms": waktu_ms, "keterangan": keterangan})
        waktu = f"{waktu_ms:9.1f} ms" if waktu_ms is not None else " " * 12
        print(f"[{'LULUS' if lulus else 'GAGAL'}] {nama:<54} {waktu}  {keterangan}")

    def jalankan(self, nama: str, uji, referensi=None, bandingkan=None):
        """Jalankan `uji()` (waktunya diukur), bandingkan dengan `referensi()` lewat `bandingkan(hasil, harap) -> (ok, ket)`.

        Tanpa `referensi`, `bandingkan(hasil, None)` hanya memeriksa hasilnya sendiri. Error apa pun dicatat sebagai GAGAL.
        Mengembalikan hasil `uji()` (atau None kalau error) supaya bisa ditampilkan di sel notebook.
        """
        hasil = None
        try:
            hasil, ms = ukur(uji)
            harap = referensi() if referensi else None
            ok, ket = bandingkan(hasil, harap) if bandingkan else (True, "")
        except (Exception, SystemExit) as exc:   # tes yang error = GAGAL, bukan alasan menghentikan notebook
            # SystemExit ikut ditangkap: fungsi proyek memakai fail() untuk pesan error ramah (Neo4j mati, login ditolak, dst.)
            self.catat(nama, False, f"error: {type(exc).__name__}: {exc}")
            return None
        self.catat(nama, bool(ok), ket, ms)
        return hasil

    @contextmanager
    def aman(self, nama: str):
        """Blok `with tes.aman("nama"):` - error di dalamnya dicatat GAGAL, bukan menghentikan notebook (Run All tetap sampai akhir)."""
        try:
            yield
        except (Exception, SystemExit) as exc:
            self.catat(nama, False, f"error: {type(exc).__name__}: {exc}")

    def tabel(self) -> pd.DataFrame:
        return pd.DataFrame(self.baris)

    def ringkasan(self) -> pd.DataFrame:
        """Cetak vonis (jumlah LULUS/GAGAL) dan kembalikan tabel semua tes."""
        t = self.tabel()
        lulus, gagal = int((t["hasil"] == "LULUS").sum()), int((t["hasil"] == "GAGAL").sum())
        print(f"HASIL: {lulus} LULUS, {gagal} GAGAL dari {len(t)} tes.")
        if gagal:
            print("Yang GAGAL:")
            for r in t[t["hasil"] == "GAGAL"].itertuples():
                print(f"  - {r.tes}: {r.keterangan}")
        else:
            print("Semua tes lulus.")
        return t
