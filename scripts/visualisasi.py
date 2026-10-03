"""Fungsi menggambar untuk notebooks/1_tes_semua.ipynb.

Butuh matplotlib + networkx (lihat requirements-notebook.txt); script 01-04 tidak memakai modul ini.
Semua gambar murni lokal (tanpa CDN/font/JS dari internet) dan memakai palet referensi slot 1-3
(biru, oranye, aqua) yang sudah divalidasi: aqua <3:1 terhadap latar, jadi identitas selalu dibantu
legenda dan label langsung. Setiap fungsi mengembalikan matplotlib Figure.
"""
from __future__ import annotations

import math
from collections import defaultdict

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib import patheffects
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle
from matplotlib.ticker import FuncFormatter

SURFACE, GRID, AXIS = "#fcfcfb", "#e1e0d9", "#c3c2b7"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
BIRU, ORANYE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"   # slot kategorikal 1-3
HEADER = "#f0efec"


# --------------------------------------------------------------------------
# Dasar
# --------------------------------------------------------------------------
def _kanvas(lebar: float, tinggi: float):
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(lebar, tinggi), dpi=110, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    return fig, ax


def _judul(ax, judul: str, subjudul: str | None = None, pad: int = 30) -> None:
    """Judul (tinta utama) di atas subjudul (tinta kedua); jarak dalam poin, bukan pecahan tinggi sumbu."""
    ax.set_title(judul, loc="left", color=INK, fontsize=11.5, pad=pad)
    if subjudul:
        ax.annotate(subjudul, xy=(0, 1), xycoords="axes fraction", xytext=(0, 8), textcoords="offset points",
                    color=INK2, fontsize=9, va="bottom", annotation_clip=False)


def _halo(teks) -> None:
    """Beri garis tepi warna latar pada teks supaya tetap terbaca di atas garis/titik."""
    teks.set_path_effects([patheffects.withStroke(linewidth=3, foreground=SURFACE)])


def _sumbu_bersih(ax, grid: str = "y") -> None:
    for sisi in ("top", "right"):
        ax.spines[sisi].set_visible(False)
    for sisi in ("left", "bottom"):
        ax.spines[sisi].set_color(AXIS)
        ax.spines[sisi].set_linewidth(0.8)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    if grid:
        ax.grid(axis=grid, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def _ribuan(v: float) -> str:
    return f"{v:,.0f}"


def simpan(fig, nama: str) -> str:
    """Simpan gambar sebagai docs/visualisasi/<nama>.png (latar sama dengan tampilan), kembalikan path relatifnya."""
    from common import PROJECT_ROOT   # impor di sini: modul ini juga bisa dipakai tanpa folder proyek lengkap

    tujuan = PROJECT_ROOT / "docs" / "visualisasi"
    tujuan.mkdir(parents=True, exist_ok=True)
    fig.savefig(tujuan / f"{nama}.png", dpi=110, facecolor=SURFACE, bbox_inches="tight")
    return f"docs/visualisasi/{nama}.png"


# --------------------------------------------------------------------------
# Perbandingan SQLite vs Neo4j (hasil scripts/eksperimen.py)
# --------------------------------------------------------------------------
def _tick_bersih(lo: float, hi: float) -> list[float]:
    """Tick 1-2-5 per dekade di dalam rentang data."""
    return [m * 10 ** k for k in range(-3, 9) for m in (1, 2, 5) if lo / 1.6 <= m * 10 ** k <= hi * 1.6]


def _tick_dekade(lo: float, hi: float) -> list[float]:
    """Tick pada pangkat 10 di dalam rentang data (untuk sumbu x yang lebar)."""
    return [10.0 ** k for k in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1) if lo / 1.6 <= 10.0 ** k <= hi * 1.6]


def _label_langsung(ax, titik: list[tuple[float, float, str]], x_teks: float) -> None:
    """Label di ujung kanan tiap garis, disebar vertikal (skala log) dengan garis penunjuk supaya tidak bertabrakan."""
    urut = sorted(titik, key=lambda t: t[1])
    y_label: list[float] = []
    for _, y, _ in urut:
        y_label.append(y if not y_label else max(y, y_label[-1] * 1.55))
    for (x, y, teks), yl in zip(urut, y_label):
        _halo(ax.annotate(teks, xy=(x, y), xytext=(x_teks, yl), textcoords="data", color=INK2, fontsize=9, va="center",
                          zorder=4, arrowprops=dict(arrowstyle="-", color=AXIS, lw=0.8, shrinkA=0, shrinkB=6)))


def gambar_benchmark(hasil: pd.DataFrame, ulangi: int, regresi: dict | None = None):
    """Waktu 'tepat k relasi' menurut jumlah path: dua pasangan setara (menyusuri semua path; himpunan unik), skala log."""
    seri = [  # (kolom, legenda, label langsung, warna, berisi?)
        ("sqlite_join_ms", "SQLite, JOIN berulang (semua path)", "SQLite JOIN", BIRU, True),
        ("neo4j_enum_ms", "Neo4j, count(p) (semua path)", "Neo4j semua path", ORANYE, True),
        ("sqlite_distinct_ms", "SQLite, DISTINCT per level (himpunan unik)", "SQLite DISTINCT", BIRU, False),
        ("neo4j_unik_ms", "Neo4j, tanpa count(p) (pruning)", "Neo4j pruning", ORANYE, False),
    ]
    d = hasil[hasil["jumlah_path"] > 0]
    x_min, x_max = d["jumlah_path"].min(), d["jumlah_path"].max()
    y_all = pd.concat([d[k].dropna() for k, *_ in seri])
    fig, ax = _kanvas(10, 5.4)
    ujung = []
    for kolom, nama, singkat, warna, isi in seri:
        g = d.dropna(subset=[kolom]).groupby("jumlah_path")[kolom].median().sort_index()
        ax.plot(g.index, g.values, color=warna, lw=1.5, ls="-" if isi else (0, (4, 2)), solid_capstyle="round",
                marker="o", ms=6.5, mfc=warna if isi else SURFACE, mec=warna, mew=1.6, label=nama, zorder=3)
        ujung.append((g.index[-1], g.values[-1], f"{singkat}  {g.values[-1]:,.1f} ms"))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(x_min / 1.6, x_max * 30)
    ax.set_ylim(y_all.min() / 1.7, y_all.max() * 1.7)
    ax.set_xticks(_tick_dekade(x_min, x_max))
    ax.set_yticks(_tick_bersih(y_all.min(), y_all.max()))
    ax.minorticks_off()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    _label_langsung(ax, ujung, x_max * 1.7)
    _sumbu_bersih(ax)
    ax.set_xlabel("Jumlah path k-relasi dari user awal (skala log); makin ke kanan: kedalaman k dan jumlah teman makin besar",
                  color=INK2, fontsize=9.5, labelpad=8)
    ax.set_ylabel("Waktu (ms, skala log)", color=INK2, fontsize=9.5, labelpad=8)
    ax.legend(loc="upper left", frameon=False, labelcolor=INK2, fontsize=8.8, handlelength=2.2)
    sub = f"Median {ulangi} pengukuran per titik. Garis penuh: menyusuri semua path. Garis putus-putus: hanya himpunan unik."
    if regresi:
        sub += (f" Per path: SQLite JOIN {regresi['sqlite_join']['b_mikrodetik_per_path']:.2f} µs, "
                f"Neo4j {regresi['neo4j_enum']['b_mikrodetik_per_path']:.2f} µs.")
    _judul(ax, "Menyusuri semua path: SQLite dan Neo4j mirip. Himpunan unik: Neo4j memangkas, SQL perlu ditulis ulang", sub)
    return fig


def gambar_keluarga_query(baris: list[tuple[str, float]], subjudul: str):
    """Rasio waktu SQLite / Neo4j per keluarga query pada skala log. Kanan 1x = Neo4j lebih cepat; kiri = SQLite lebih cepat."""
    n = len(baris)
    fig, ax = _kanvas(10.5, 0.43 * n + 2.4)
    ys = np.arange(n)[::-1]
    maks = max(abs(math.log10(r)) for _, r in baris)
    for y, (_, r) in zip(ys, baris):
        x = math.log10(r)
        ax.barh(y, x, height=0.6, color=ORANYE if r >= 1 else BIRU, zorder=2)
        teks = f"Neo4j {r:.1f}× lebih cepat" if r >= 1 else f"SQLite {1 / r:.1f}× lebih cepat"
        ax.text(x + (0.05 if x >= 0 else -0.05), y, teks, va="center", ha="left" if x >= 0 else "right", color=INK2, fontsize=9)
    ax.axvline(0, color=INK2, lw=1.0, zorder=3)
    ax.set_yticks(ys)
    ax.set_yticklabels([b for b, _ in baris])
    ax.set_xlim(-(maks + 1.15), maks + 1.15)
    ticks = [t for t in range(-3, 4) if abs(t) <= maks + 1.0]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{10 ** abs(t):g}×" if t else "sama" for t in ticks])
    _sumbu_bersih(ax, grid="x")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", colors=INK2, labelsize=9.5)
    ax.set_xlabel("← SQLite lebih cepat                                 Neo4j lebih cepat →", color=INK2, fontsize=9.5, labelpad=8)
    _judul(ax, "Siapa lebih cepat menjawab pertanyaan yang sama?", subjudul)
    return fig


def gambar_pemanasan(waktu):
    """Waktu panggilan ke-1, ke-2, ... query yang sama di Neo4j (skala log): server yang baru menyala lambat lalu stabil.

    `waktu` = satu kurva (daftar ms) atau beberapa kurva (satu per run, tiap kali Neo4j dinyalakan ulang).
    """
    kurva = [list(k) for k in waktu] if waktu and isinstance(waktu[0], (list, tuple)) else [list(waktu)]
    semua = [v for k in kurva for v in k]
    pertama = float(np.median([k[0] for k in kurva]))
    stabil = float(np.median([np.median(k[-10:]) for k in kurva]))
    fig, ax = _kanvas(9.5, 4.4)
    for i, k in enumerate(kurva):
        ax.plot(np.arange(1, len(k) + 1), k, color=ORANYE, lw=1.4, alpha=1.0 if len(kurva) == 1 else 0.75, marker="o", ms=4.5,
                mfc=ORANYE, mec=SURFACE, mew=1.0, zorder=3)
    ax.axhline(stabil, color=AXIS, lw=1.0, zorder=1)
    ax.set_yscale("log")
    ax.set_yticks(_tick_bersih(min(semua), max(semua)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.minorticks_off()
    _halo(ax.annotate(f"panggilan pertama: sekitar {pertama:,.0f} ms", xy=(1, max(k[0] for k in kurva)), xytext=(3.5, max(k[0] for k in kurva)),
                      color=INK2, fontsize=9, va="center"))
    _halo(ax.text(max(len(k) for k in kurva), stabil * 1.18, f"stabil \u2248 {stabil:,.0f} ms ({pertama / stabil:,.0f}\u00d7 lebih cepat)",
                  color=INK2, fontsize=9, ha="right", va="bottom"))
    _sumbu_bersih(ax)
    ax.set_xlabel("Panggilan ke-n dengan query yang sama (user dan parameter tetap)", color=INK2, fontsize=9.5, labelpad=8)
    ax.set_ylabel("Waktu (ms, skala log)", color=INK2, fontsize=9.5, labelpad=8)
    sub = "JVM mengompilasi kode saat dipakai (JIT) dan rencana query dibuat saat pertama kali dijalankan."
    if len(kurva) > 1:
        sub += f" Satu garis per run ({len(kurva)} run, Neo4j dinyalakan ulang tiap run)."
    _judul(ax, "Neo4j yang baru menyala lambat pada panggilan pertama, lalu stabil", sub)
    return fig


def gambar_skala(df: pd.DataFrame):
    """Waktu 'tepat 3 relasi' dari hub pada graf yang makin besar (sampel Pokec lalu graf sintetis), skala log."""
    seri = [("sqlite_join_ms", "SQLite JOIN", BIRU, True), ("neo4j_enum_ms", "Neo4j semua path", ORANYE, True),
            ("sqlite_distinct_ms", "SQLite DISTINCT", BIRU, False), ("neo4j_unik_ms", "Neo4j pruning", ORANYE, False)]
    d = df.sort_values("n_edge")
    x_min, x_max = d["n_edge"].min(), d["n_edge"].max()
    y_all = pd.concat([d[k] for k, *_ in seri])
    fig, ax = _kanvas(9.5, 4.8)
    ujung = []
    for kolom, nama, warna, isi in seri:
        ax.plot(d["n_edge"], d[kolom], color=warna, lw=1.5, ls="-" if isi else (0, (4, 2)), marker="o", ms=6.5,
                mfc=warna if isi else SURFACE, mec=warna, mew=1.6, zorder=3)
        ujung.append((x_max, d[kolom].iloc[-1], f"{nama}  {d[kolom].iloc[-1]:,.0f} ms"))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(x_min / 1.3, x_max * 4)
    ax.set_ylim(y_all.min() / 1.7, y_all.max() * 1.7)
    ax.set_xticks(d["n_edge"])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_yticks(_tick_bersih(y_all.min(), y_all.max()))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.minorticks_off()
    _label_langsung(ax, ujung, x_max * 1.35)
    _sumbu_bersih(ax)
    ax.set_xlabel("Jumlah edge pada graf (skala log): sampel Pokec, lalu graf sintetis yang lebih besar", color=INK2,
                  fontsize=9.5, labelpad=8)
    ax.set_ylabel("Waktu (ms, skala log)", color=INK2, fontsize=9.5, labelpad=8)
    tumbuh = {kolom: float(d[kolom].iloc[-1] / d[kolom].iloc[0]) for kolom, *_ in seri}
    _judul(ax, f"Graf {x_max / x_min:.1f}\u00d7 lebih besar: waktu naik {min(tumbuh.values()):.1f}\u00d7 sampai {max(tumbuh.values()):.1f}\u00d7",
           "Hub (out-degree terbesar), tepat 3 relasi. Graf sintetis: preferential attachment (Barabási–Albert), dimuat sementara.")
    return fig


def gambar_strategi_hybrid(df: pd.DataFrame):
    """'Teman dari teman, pria 20-30 tahun' dengan tiga strategi, per user uji (batang berkelompok, skala log)."""
    seri = [("s1_sql_ms", "S1 semua di SQLite", BIRU), ("s2_neo4j_ms", "S2 semua di Neo4j (atribut diduplikasi)", ORANYE),
            ("s3_hybrid_ms", "S3 hybrid (id dari Neo4j, filter di SQLite)", AQUA)]
    kolom_waktu = [k for k, *_ in seri]
    d = df.sort_values("out_degree", ascending=False).reset_index(drop=True)
    fig, ax = _kanvas(10, 4.9)
    lebar = 0.26
    for i, (kolom, nama, warna) in enumerate(seri):
        pos = np.arange(len(d)) + (i - 1) * (lebar + 0.02)
        ax.bar(pos, d[kolom], width=lebar, color=warna, label=nama, zorder=2)
        for p, v in zip(pos, d[kolom]):
            ax.text(p, v * 1.12, f"{v:.1f}", ha="center", va="bottom", color=INK2, fontsize=8)
    ax.set_yscale("log")
    ax.set_ylim(d[kolom_waktu].min().min() / 1.6, d[kolom_waktu].max().max() * 2.6)
    ax.set_yticks(_tick_bersih(d[kolom_waktu].min().min(), d[kolom_waktu].max().max()))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.minorticks_off()
    ax.set_xticks(np.arange(len(d)))
    ax.set_xticklabels([f"user {u}\n{int(o)} teman\n{int(k):,} id ke SQLite" for u, o, k in
                        zip(d["user_id"], d["out_degree"], d["id_dikirim_ke_sqlite"])], fontsize=8.5)
    _sumbu_bersih(ax)
    ax.set_ylabel("Waktu (ms, skala log)", color=INK2, fontsize=9.5, labelpad=8)
    ax.legend(loc="upper right", frameon=False, labelcolor=INK2, fontsize=8.8)
    _judul(ax, "Strategi hybrid membayar ongkos lintas batas, tetapi tidak perlu menduplikasi atribut",
           "Teman dari teman (tepat 2 relasi) yang pria berumur 20–30; hasil ketiga strategi identik. Median per user.")
    return fig


def gambar_lintas_batas(df: pd.DataFrame):
    """Waktu mengambil atribut N user: dari SQLite (IN (...)) vs dari node Neo4j, skala log-log."""
    fig, ax = _kanvas(9.2, 4.4)
    for kolom, nama, warna in (("sqlite_ms", "SQLite", BIRU), ("neo4j_ms", "Neo4j", ORANYE)):
        ax.plot(df["n_user"], df[kolom], color=warna, lw=1.5, marker="o", ms=6.5, mfc=warna, mec=SURFACE, mew=1.3, zorder=3)
        _halo(ax.annotate(f"{nama}\n{df[kolom].iloc[-1]:,.1f} ms", xy=(df["n_user"].iloc[-1], df[kolom].iloc[-1]),
                          xytext=(10, 0), textcoords="offset points", color=INK2, fontsize=9, va="center"))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(df["n_user"].min() / 1.5, df["n_user"].max() * 4)
    ax.set_xticks(df["n_user"])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_yticks(_tick_bersih(df[["sqlite_ms", "neo4j_ms"]].min().min(), df[["sqlite_ms", "neo4j_ms"]].max().max()))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.minorticks_off()
    _sumbu_bersih(ax)
    ax.set_xlabel("Jumlah user yang atributnya diambil (skala log)", color=INK2, fontsize=9.5, labelpad=8)
    ax.set_ylabel("Waktu (ms, skala log)", color=INK2, fontsize=9.5, labelpad=8)
    nisbah = float(df["neo4j_ms"].iloc[-1] / df["sqlite_ms"].iloc[-1])
    n_akhir = int(df["n_user"].iloc[-1])
    _judul(ax, f"Mengambil atribut {n_akhir:,} user: SQLite {nisbah:.0f}\u00d7 lebih cepat daripada membaca node Neo4j",
           "Median dari pengambilan n user; SQLite memakai IN (...) lalu pandas, Neo4j memakai MATCH ... WHERE IN.")
    return fig


# --------------------------------------------------------------------------
# Graf (data dari Neo4j, atribut dari SQLite)
# --------------------------------------------------------------------------
def _urutan_cincin(simpul: list[int], tetangga: dict[int, set[int]]) -> list[int]:
    """Urutkan simpul di sebuah cincin agar yang saling terhubung berdekatan (rantai tetangga terdekat)."""
    sisa = set(simpul)
    mulai = max(simpul, key=lambda s: (len(tetangga[s] & sisa), -s))
    urut = [mulai]
    sisa.remove(mulai)
    while sisa:
        akhir = urut[-1]
        berikut = max(sisa, key=lambda s: (len(tetangga[s] & tetangga[akhir]) + (s in tetangga[akhir]), -s))
        urut.append(berikut)
        sisa.remove(berikut)
    return urut


def gambar_jaringan_ego(pusat: int, teman: list[int], kandidat: list[tuple[int, int]], relasi: list[tuple[int, int]]):
    """Gambar jaringan di sekitar satu user: dia (tengah), teman langsung (cincin dalam), kandidat rekomendasi (luar).

    `kandidat` = [(user_id, jumlah_teman_bersama)], `relasi` = pasangan (sumber, tujuan) FRIEND di antara semuanya.
    Garis tidak berarah (satu relasi di arah mana pun sudah dihitung terhubung).
    """
    teman = [int(t) for t in teman]
    kandidat = [(int(u), int(n)) for u, n in kandidat]
    k_ids = [u for u, _ in kandidat]
    k_set = set(k_ids)
    pusat = int(pusat)
    pasangan = {frozenset((int(a), int(b))) for a, b in relasi if int(a) != int(b)}
    tetangga: dict[int, set[int]] = defaultdict(set)
    for p in pasangan:
        a, b = tuple(p)
        tetangga[a].add(b)
        tetangga[b].add(a)

    fig, ax = _kanvas(9.0, 6.9)
    if not teman:
        ax.text(0.5, 0.5, "User ini belum punya teman (relasi FRIEND keluar).", ha="center", va="center",
                color=INK2, transform=ax.transAxes)
        ax.axis("off")
        return fig

    tau = 2 * math.pi
    urutan = _urutan_cincin(teman, tetangga)
    sudut = {t: tau * i / len(urutan) for i, t in enumerate(urutan)}
    pos = {pusat: (0.0, 0.0)}
    pos.update({t: (math.cos(a), math.sin(a)) for t, a in sudut.items()})

    # Kandidat: di sudut rata-rata teman penghubungnya; digeser sedikit bila saling berdempetan.
    sk = {}
    for u in k_ids:
        a = [sudut[t] for t in tetangga[u] if t in sudut]
        sk[u] = math.atan2(sum(map(math.sin, a)), sum(map(math.cos, a))) % tau if a else 0.0
    urut_k = sorted(k_ids, key=lambda u: sk[u])
    for i in range(1, len(urut_k)):
        sk[urut_k[i]] = max(sk[urut_k[i]], sk[urut_k[i - 1]] + 0.3)
    for u in k_ids:
        pos[u] = (1.75 * math.cos(sk[u]), 1.75 * math.sin(sk[u]))

    abu, biru, oranye = [], [], []
    for p in pasangan:
        a, b = tuple(p)
        if a not in pos or b not in pos:
            continue
        seg = (pos[a], pos[b])
        if pusat in p:
            biru.append(seg)
        elif (a in k_set) != (b in k_set):
            oranye.append(seg)
        else:
            abu.append(seg)
    ax.add_collection(LineCollection(abu, colors=AXIS, linewidths=0.6, alpha=0.85, zorder=1))
    ax.add_collection(LineCollection(biru, colors=BIRU, linewidths=0.9, alpha=0.55, zorder=1))
    ax.add_collection(LineCollection(oranye, colors=ORANYE, linewidths=1.1, alpha=0.7, zorder=1))

    ring = dict(edgecolors=SURFACE, linewidths=1.5, zorder=3)
    ax.scatter(*zip(*[pos[t] for t in teman]), s=75, c=AQUA, **ring)
    ax.scatter(*zip(*[pos[u] for u in k_ids]), s=170, c=ORANYE, **ring) if k_ids else None
    ax.scatter([0], [0], s=300, c=BIRU, **ring)

    _halo(ax.text(0, 0.17, str(pusat), ha="center", va="bottom", color=INK, fontsize=9, fontweight="bold", zorder=5))
    for u, n in kandidat:
        x, y = pos[u]
        _halo(ax.text(x * 1.1, y * 1.1, f"{u}\n{n} teman bersama", ha="left" if x >= 0 else "right",
                      va="bottom" if y >= 0 else "top", color=INK2, fontsize=8.5, zorder=5))

    handel = [
        Line2D([], [], marker="o", ls="", color=BIRU, mec=SURFACE, mew=1.2, ms=12, label=f"User demo ({pusat})"),
        Line2D([], [], marker="o", ls="", color=AQUA, mec=SURFACE, mew=1.2, ms=9, label=f"Teman langsung ({len(teman)})"),
        Line2D([], [], marker="o", ls="", color=ORANYE, mec=SURFACE, mew=1.2, ms=11, label=f"Kandidat rekomendasi ({len(kandidat)})"),
        Line2D([], [], color=BIRU, lw=1.2, alpha=0.7, label="user demo - teman"),
        Line2D([], [], color=ORANYE, lw=1.4, alpha=0.8, label="teman - kandidat"),
        Line2D([], [], color=AXIS, lw=1.0, label="antar-teman lain"),
    ]
    ax.legend(handles=handel, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=3, frameon=False,
              labelcolor=INK2, fontsize=8.5, columnspacing=1.8)
    # Batas sumbu dari posisi node sebenarnya (+ ruang untuk label kandidat), bukan angka tetap.
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    ax.set_xlim(min(xs) * 1.1 - 1.3, max(xs) * 1.1 + 1.3)
    ax.set_ylim(min(ys) * 1.1 - 0.4, max(ys) * 1.1 + 0.7)
    ax.set_aspect("equal")
    ax.axis("off")
    _judul(ax, "Jaringan di sekitar user demo: dari teman langsung ke kandidat rekomendasi",
           "Struktur dari Neo4j (relasi FRIEND, arah diabaikan); kandidat = hasil rekomendasi_teman().")
    return fig


def gambar_klaster(anggota: pd.DataFrame, relasi: list[tuple[int, int]], hobi: str, maks_simpul: int = 150):
    """Gambar satu klaster hobi: bentuk jaringan dari Neo4j, warna = gender dari SQLite, ukuran = jumlah teman di klaster.

    `anggota` punya kolom user_id, gender (1 pria / 0 wanita / NA), teman_dalam_klaster. Klaster besar dipangkas
    ke `maks_simpul` anggota paling terhubung supaya gambar tetap terbaca.
    """
    df = anggota[["user_id", "gender", "teman_dalam_klaster"]].copy()
    total = len(df)
    if total > maks_simpul:
        df = df.sort_values("teman_dalam_klaster", ascending=False).head(maks_simpul)
    ids = {int(u) for u in df["user_id"]}
    g = nx.Graph()
    g.add_nodes_from(ids)
    g.add_edges_from((int(a), int(b)) for a, b in relasi if int(a) in ids and int(b) in ids and int(a) != int(b))
    pos = nx.spring_layout(g, seed=7, k=1.5 / math.sqrt(max(len(g), 1)), iterations=300)

    fig, ax = _kanvas(9.5, 7)
    ax.add_collection(LineCollection([(pos[a], pos[b]) for a, b in g.edges], colors=AXIS, linewidths=0.9, zorder=1))
    gender = {int(u): g_ for u, g_ in zip(df["user_id"], df["gender"])}
    warna = {1: BIRU, 0: ORANYE}
    n_per = {1: 0, 0: 0, None: 0}
    for node in g.nodes:
        gn = gender[node]
        gn = None if pd.isna(gn) else int(gn)
        n_per[gn] += 1
        ax.scatter(*pos[node], s=45 + 26 * g.degree[node], c=warna.get(gn, MUTED), edgecolors=SURFACE, linewidths=1.5, zorder=3)
    arah = [(14, 14, "left"), (16, 16, "left"), (14, -16, "left")]   # tiga label hub menjauh ke arah berbeda
    for node, (dx, dy, ha) in zip(sorted(g.nodes, key=lambda n: (-g.degree[n], n))[:3], arah):
        x, y = pos[node]
        _halo(ax.annotate(str(node), (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, color=INK2, fontsize=8.5,
                          zorder=5, arrowprops=dict(arrowstyle="-", color=AXIS, lw=0.8, shrinkB=5)))

    handel = [
        Line2D([], [], marker="o", ls="", color=BIRU, mec=SURFACE, mew=1.2, ms=10, label=f"Pria ({n_per[1]})"),
        Line2D([], [], marker="o", ls="", color=ORANYE, mec=SURFACE, mew=1.2, ms=10, label=f"Wanita ({n_per[0]})"),
    ]
    if n_per[None]:
        handel.append(Line2D([], [], marker="o", ls="", color=MUTED, mec=SURFACE, mew=1.2, ms=10, label=f"Tidak diisi ({n_per[None]})"))
    ax.legend(handles=handel, loc="upper left", bbox_to_anchor=(-0.02, 1.0), frameon=False, labelcolor=INK2, fontsize=9)
    ax.margins(0.08)
    ax.set_aspect("equal")
    ax.axis("off")
    catatan = f"menampilkan {len(g)} dari {total} anggota paling terhubung; " if total > maks_simpul else ""
    _judul(ax, f"Klaster teman sehobi “{hobi}”: {len(g)} user, {g.number_of_edges()} pertemanan",
           f"{catatan}Bentuk dari Neo4j; warna = gender dari SQLite; ukuran titik = jumlah teman di klaster.")
    return fig


def gambar_distribusi_derajat(derajat: pd.DataFrame):
    """Histogram jumlah relasi FRIEND (masuk + keluar) per user, dengan hub terbesar diberi label."""
    nilai = derajat["total_degree"].to_numpy()
    lebar = 20
    batas = np.arange(0, nilai.max() + lebar, lebar)
    jumlah, tepi = np.histogram(nilai, bins=batas)
    fig, ax = _kanvas(9.5, 4.6)
    ax.bar(tepi[:-1], jumlah, width=lebar - 2, align="edge", color=BIRU, zorder=2)
    _sumbu_bersih(ax)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _ribuan(v)))
    hub = derajat.sort_values("total_degree", ascending=False).iloc[0]
    ax.annotate(f"hub terbesar: user {int(hub['user_id'])}\n{int(hub['total_degree'])} relasi", (hub["total_degree"], 0),
                xytext=(-12, 60), textcoords="offset points", ha="right", color=INK2, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=AXIS, lw=0.8, shrinkB=2))
    ax.set_xlabel("Jumlah relasi FRIEND per user (masuk + keluar), dikelompokkan per 20", color=INK2, fontsize=9.5, labelpad=8)
    ax.set_ylabel("Jumlah user", color=INK2, fontsize=9.5, labelpad=8)
    _judul(ax, "Sebagian besar user punya sedikit relasi; hanya segelintir yang menjadi hub",
           f"{len(derajat):,} user; median {int(np.median(nilai))} relasi per user (derajat dihitung di Neo4j).")
    return fig


def gambar_model_graf(properti: pd.DataFrame, jumlah: pd.DataFrame):
    """Diagram model data di Neo4j: node User dan Hobby, relasi FRIEND dan HAS_HOBBY (properti/jumlah dibaca dari database)."""
    fig, ax = _kanvas(10, 6.4)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.4)
    ax.set_aspect("equal")
    ax.axis("off")
    n = {(r.jenis, r.nama): int(r.jumlah) for r in jumlah.itertuples()}
    pos = {"User": (2.7, 3.0), "Hobby": (7.4, 3.0)}
    warna = {"User": (BIRU, "#ffffff"), "Hobby": (ORANYE, INK)}   # teks di dalam isian: putih atau tinta menurut luminansi
    for nama, (x, y) in pos.items():
        ax.add_patch(Circle((x, y), 0.95, fc=warna[nama][0], ec=SURFACE, lw=2, zorder=3))
        ax.text(x, y + 0.12, nama, ha="center", va="center", color=warna[nama][1], fontsize=13, fontweight="bold", zorder=4)
        ax.text(x, y - 0.3, f"{n[('node', nama)]:,} node", ha="center", va="center", color=warna[nama][1], fontsize=9.5, zorder=4)
        props = properti[properti["label"] == nama]
        isi = "\n".join(f"{r.properti}  ({r.tipe})" for r in props.itertuples())
        ax.text(x, y - 1.2, "Properti\n" + isi, ha="center", va="top", color=INK2, fontsize=9, linespacing=1.5, zorder=4,
                bbox=dict(boxstyle="round,pad=0.5", fc=HEADER, ec=AXIS, lw=0.8))
    # FRIEND: relasi User -> User (lingkaran ke dirinya sendiri)
    x, y = pos["User"]
    ax.add_patch(FancyArrowPatch((x - 0.55, y + 0.78), (x + 0.55, y + 0.78), connectionstyle="arc3,rad=-1.9",
                                 arrowstyle="-|>", mutation_scale=14, color=INK2, lw=1.4, zorder=2))
    ax.text(x, y + 1.95, f"FRIEND  ({n[('relasi', 'FRIEND')]:,} relasi, berarah)", ha="center", va="bottom", color=INK2, fontsize=9.5)
    # HAS_HOBBY: User -> Hobby
    ax.add_patch(FancyArrowPatch((pos["User"][0] + 0.98, y), (pos["Hobby"][0] - 0.98, y), arrowstyle="-|>",
                                 mutation_scale=14, color=INK2, lw=1.4, zorder=2))
    ax.text((pos["User"][0] + pos["Hobby"][0]) / 2, y + 0.12, f"HAS_HOBBY\n{n[('relasi', 'HAS_HOBBY')]:,} relasi",
            ha="center", va="bottom", color=INK2, fontsize=9.5)
    ax.text(0, 6.35, "Model graf di Neo4j", color=INK, fontsize=11.5, va="top")
    ax.text(0, 5.98, "Jumlah dan properti dibaca dari database; node User hanya menyimpan atribut ringan.",
            color=INK2, fontsize=9, va="top")
    return fig


def baca_skema_sqlite(conn) -> dict:
    """Baca skema nyata SQLite: kolom, tipe, primary key, foreign key, dan jumlah baris tiap tabel."""
    skema = {}
    nama_tabel = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for nama in nama_tabel:
        kolom = [(r[1], r[2] or "", bool(r[5])) for r in conn.execute(f"PRAGMA table_info({nama})")]
        fk = [(r[3], r[2], r[4]) for r in conn.execute(f"PRAGMA foreign_key_list({nama})")]   # (kolom, tabel_tujuan, kolom_tujuan)
        skema[nama] = {"kolom": kolom, "fk": fk, "baris": conn.execute(f"SELECT COUNT(*) FROM {nama}").fetchone()[0]}
    return skema


def gambar_skema_sqlite(skema: dict):
    """Diagram tabel SQLite (gaya ER): kolom, tipe, PK/FK, jumlah baris, dan garis foreign key."""
    baris_h, kepala, lebar_kotak = 0.27, 0.55, 3.9
    tinggi = {t: kepala + baris_h * len(v["kolom"]) for t, v in skema.items()}
    kiri = [t for t in skema if t == "users"]
    kanan = [t for t in skema if t != "users"]
    atas = max(tinggi.get("users", 0), sum(tinggi[t] for t in kanan) + 0.8 * len(kanan)) + 1.3
    fig, ax = _kanvas(10.5, atas * 0.9 + 0.6)
    ax.set_xlim(0, 10.5)
    ax.set_ylim(0, atas)
    ax.set_aspect("equal")
    ax.axis("off")

    letak = {}
    for t in kiri:
        letak[t] = (0.4, atas - 1.0)
    y = atas - 1.0
    for t in kanan:
        letak[t] = (6.2, y)
        y -= tinggi[t] + 0.8

    baris_y = {}
    for t, v in skema.items():
        x0, y0 = letak[t]
        ax.add_patch(Rectangle((x0, y0 - tinggi[t]), lebar_kotak, tinggi[t], fc=SURFACE, ec=AXIS, lw=1.0, zorder=2))
        ax.add_patch(Rectangle((x0, y0 - kepala), lebar_kotak, kepala, fc=HEADER, ec=AXIS, lw=1.0, zorder=2))
        ax.text(x0 + 0.15, y0 - kepala / 2, t, va="center", color=INK, fontsize=11, fontweight="bold", zorder=3)
        ax.text(x0 + lebar_kotak - 0.15, y0 - kepala / 2, f"{v['baris']:,} baris", va="center", ha="right", color=INK2, fontsize=9, zorder=3)
        fk_kolom = {k for k, _, _ in v["fk"]}
        for i, (nama, tipe, pk) in enumerate(v["kolom"]):
            yy = y0 - kepala - baris_h * (i + 0.5)
            baris_y[(t, nama)] = yy
            tag = ", ".join(x for x, ada in (("PK", pk), ("FK", nama in fk_kolom)) if ada)
            ax.text(x0 + 0.15, yy, nama, va="center", color=INK, fontsize=8.8, zorder=3)
            ax.text(x0 + 2.35, yy, tag, va="center", color=INK2, fontsize=8, fontweight="bold", zorder=3)
            ax.text(x0 + lebar_kotak - 0.15, yy, tipe.lower(), va="center", ha="right", color=MUTED, fontsize=8.5, zorder=3)
    for t, v in skema.items():
        for kolom, tujuan, kolom_tujuan in v["fk"]:
            if tujuan not in letak:
                continue
            xa, ya = letak[t][0], baris_y[(t, kolom)]
            xb, yb = letak[tujuan][0] + lebar_kotak, baris_y[(tujuan, kolom_tujuan)]
            ax.add_patch(FancyArrowPatch((xa, ya), (xb, yb), arrowstyle="-", color=INK2, lw=1.3, zorder=1,
                                         connectionstyle="arc3,rad=0.0"))
            ax.text(xa - 0.2, ya - 0.3, "N", color=INK2, fontsize=9, ha="right", fontweight="bold")   # di luar jalur garis
            ax.text(xb + 0.2, yb + 0.12, "1", color=INK2, fontsize=9, ha="left", fontweight="bold")
    ax.text(0, atas - 0.1, "Skema relasional di SQLite", color=INK, fontsize=11.5, va="top")
    catatan = "Skema dibaca langsung dari database (PRAGMA). "
    if "friendships" in skema:
        catatan += "friendships hanyalah salinan edge untuk benchmark (tanpa foreign key)."
    ax.text(0, atas - 0.5, catatan, color=INK2, fontsize=9, va="top")
    return fig


# --------------------------------------------------------------------------
# Grafik dari tabel (SQLite)
# --------------------------------------------------------------------------
def gambar_batang_horizontal(df: pd.DataFrame, kolom_label: str, kolom_nilai: str, judul: str, subjudul: str | None = None):
    """Batang horizontal satu seri (satu warna), nilai tertulis di ujung batang, terurut dari terbesar di atas."""
    d = df.sort_values(kolom_nilai, ascending=True)
    fig, ax = _kanvas(9.5, 0.36 * len(d) + 1.9)
    ax.barh(d[kolom_label].astype(str), d[kolom_nilai], height=0.62, color=BIRU, zorder=2)
    maks = d[kolom_nilai].max()
    for i, v in enumerate(d[kolom_nilai]):
        ax.text(v + maks * 0.012, i, _ribuan(v), va="center", ha="left", color=INK2, fontsize=9)
    _sumbu_bersih(ax, grid="")
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xticks([])
    ax.tick_params(axis="y", colors=INK2, labelsize=9.5)
    ax.set_xlim(0, maks * 1.12)
    _judul(ax, judul, subjudul)
    return fig


def gambar_histogram(nilai, judul: str, subjudul: str, label_x: str, lebar_kelompok: int = 2):
    """Histogram satu seri; median diberi label langsung."""
    nilai = np.asarray(list(nilai), dtype=float)
    batas = np.arange(np.floor(nilai.min()), nilai.max() + lebar_kelompok, lebar_kelompok)
    jumlah, tepi = np.histogram(nilai, bins=batas)
    fig, ax = _kanvas(9.5, 4.4)
    ax.bar(tepi[:-1], jumlah, width=lebar_kelompok * 0.88, align="edge", color=BIRU, zorder=2)
    _sumbu_bersih(ax)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _ribuan(v)))
    med = float(np.median(nilai))
    atas = jumlah.max() * 1.12
    ax.set_ylim(0, jumlah.max() * 1.2)
    ax.plot([med, med], [0, atas], color=INK2, lw=1.0, zorder=3)          # garis tipis penanda median
    ax.text(med + lebar_kelompok * 0.35, atas, f"median {med:g}", va="center", ha="left", color=INK2, fontsize=9)
    ax.set_xlabel(label_x, color=INK2, fontsize=9.5, labelpad=8)
    ax.set_ylabel("Jumlah user", color=INK2, fontsize=9.5, labelpad=8)
    _judul(ax, judul, subjudul)
    return fig
