"""Gabungkan hasil beberapa run notebook 1 menjadi angka gabungan (median antar-run) beserta rentang antar-run.

Mengapa: JVM Neo4j berbeda tiap kali dinyalakan (JIT, garbage collection, cache), sehingga satu run saja bisa menyimpang. Georges dkk.
(2007) menganjurkan beberapa invokasi VM dan melaporkan ukuran sebaran. Cara pakai:

  1. Jalankan notebook 1 beberapa kali, tiap run ke subfolder sendiri (Neo4j mati lalu menyala lagi tiap run), mis. di PowerShell:
        $env:HASIL_SUBDIR = "run1"; jupyter nbconvert --to notebook --execute --inplace notebooks/1_tes_semua.ipynb
        (ulangi untuk run2, run3)
  2. python scripts/rangkum_run.py run1 run2 run3

Keluarannya: docs/hasil/gabungan/*.csv|json dan gambar docs/visualisasi/ yang digambar ulang dari median antar-run.
Script ini murni membaca berkas; tidak memerlukan Neo4j.
"""
from __future__ import annotations

import json
import sys

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd

import eksperimen as ek
import visualisasi as viz
from common import PROJECT_ROOT

HASIL = PROJECT_ROOT / "docs" / "hasil"


def baca(subdir: str, nama: str) -> pd.DataFrame:
    return pd.read_csv(HASIL / subdir / f"{nama}.csv")


def gabung(runs: list[str], nama: str, kunci: list[str]) -> pd.DataFrame:
    """Median, minimum, dan maksimum antar-run untuk tiap kolom angka, per baris kunci (urutan baris run pertama dipertahankan)."""
    semua = pd.concat([baca(r, nama).assign(_run=r) for r in runs], ignore_index=True)
    urutan = baca(runs[0], nama)[kunci].drop_duplicates()
    angka = [c for c in semua.select_dtypes("number").columns if c not in kunci]
    g = semua.groupby(kunci, sort=False)
    median = g[angka].median()
    hasil = urutan.merge(median.reset_index(), on=kunci, how="left")
    for ujung, fungsi in (("min", "min"), ("maks", "max")):
        ekstrem = g[angka].agg(fungsi).add_suffix(f"_{ujung}").reset_index()
        hasil = hasil.merge(ekstrem, on=kunci, how="left")
    non_angka = [c for c in semua.columns if c not in angka and c not in kunci and c != "_run"]
    if non_angka:   # kolom teks/bool: ambil dari run pertama; bool: benar hanya kalau benar di semua run
        pertama = baca(runs[0], nama)[kunci + non_angka].drop_duplicates(subset=kunci)
        for c in non_angka:
            if semua[c].dropna().map(lambda v: isinstance(v, (bool, np.bool_))).all() and semua[c].notna().any():
                semua_benar = semua.groupby(kunci, sort=False)[c].all().rename(c).reset_index()
                pertama = pertama.drop(columns=c).merge(semua_benar, on=kunci, how="left")
        hasil = hasil.merge(pertama, on=kunci, how="left")
    return hasil


def main() -> None:
    runs = sys.argv[1:]
    if len(runs) < 2:
        sys.exit("Pemakaian: python scripts/rangkum_run.py run1 run2 [run3 ...]  (subfolder di docs/hasil/)")
    keluar_dir = HASIL / "gabungan"
    keluar_dir.mkdir(exist_ok=True)

    def simpan(df: pd.DataFrame, nama: str) -> None:
        df.to_csv(keluar_dir / f"{nama}.csv", index=False)

    ring = gabung(runs, "ringkasan", ["keluarga"])
    # rasio gabungan = median rasio per run; pemenang konsisten bila SAMA di semua run
    per_run = pd.concat([baca(r, "ringkasan").assign(_run=r) for r in runs])
    ring["pemenang_konsisten"] = [per_run[per_run["keluarga"] == k]["pemenang"].nunique() == 1 for k in ring["keluarga"]]
    ring["pemenang"] = np.where(ring["neo4j_ms"] < ring["sqlite_ms"], "Neo4j", "SQLite")
    simpan(ring, "ringkasan")
    khop = gabung(runs, "khop", ["user_id", "k"])
    skala = gabung(runs, "skala", ["n_user", "user_id"])
    jalur = gabung(runs, "jalur", ["a", "b"])
    strategi = gabung(runs, "strategi", ["user_id"])
    lintas = gabung(runs, "lintas_batas", ["n_user"])
    dasar = gabung(runs, "dasar", ["keluarga"])
    rek = gabung(runs, "rekomendasi", ["user_id"])
    for nama, df in (("khop", khop), ("skala", skala), ("jalur", jalur), ("strategi", strategi), ("lintas_batas", lintas),
                     ("dasar", dasar), ("rekomendasi", rek)):
        simpan(df, nama)

    # regresi waktu-per-path dari data gabungan + sebaran antar-run
    reg_runs = []
    for r in runs:
        lain = json.loads((HASIL / r / "lainnya.json").read_text(encoding="utf-8"))
        reg_runs.append(lain.get("regresi_gabungan") or lain.get("regresi"))
    regresi = ek.regresi_waktu_path(pd.concat([khop, skala], ignore_index=True))
    sebaran = {n: [r[n]["b_mikrodetik_per_path"] for r in reg_runs if r] for n in ("sqlite_join", "neo4j_enum")}
    lain_pertama = json.loads((HASIL / runs[0] / "lainnya.json").read_text(encoding="utf-8"))
    kurva = [json.loads((HASIL / r / "lainnya.json").read_text(encoding="utf-8")).get("kurva_pemanasan") for r in runs]
    tes_run = {r: baca(r, "tes") for r in runs}
    ringkas_tes = {r: {"lulus": int((t["hasil"] == "LULUS").sum()), "gagal": int((t["hasil"] == "GAGAL").sum())} for r, t in tes_run.items()}

    # vonis dan jawaban dihitung ulang dari angka gabungan
    drift = lain_pertama.get("drift")
    h = {"ringkasan": ring, "skala": skala, "drift": drift, "strategi": strategi, "lintas_batas": lintas,
         "overhead": {k: float(np.median([json.loads((HASIL / r / "lainnya.json").read_text(encoding="utf-8"))["overhead"][k] for r in runs]))
                      for k in ("sqlite_ms", "neo4j_ms", "neo4j_server_ms")}}
    vonis = ek.vonis_hipotesis(h, tes_run[runs[0]])
    simpan(vonis, "vonis")
    jawaban = ek.jawaban_dosen(h, tes_run[runs[0]])
    lainnya = {"runs": runs, "tes_per_run": ringkas_tes, "regresi_gabungan": regresi, "biaya_per_path_antar_run": sebaran,
               "overhead_median": h["overhead"], "penyimpanan_run_pertama": lain_pertama.get("penyimpanan"),
               "lingkungan": lain_pertama.get("lingkungan"), "profil_graf": lain_pertama.get("profil_graf"),
               "kurva_pemanasan_per_run": kurva, "kecepatan_per_run": {r: json.loads((HASIL / r / "lainnya.json").read_text(encoding="utf-8")).get("kecepatan") for r in runs},
               "jawaban": jawaban}
    (keluar_dir / "lainnya.json").write_text(json.dumps(lainnya, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    # gambar dari median antar-run
    n = len(runs)
    viz.simpan(viz.gambar_benchmark(khop, 5 * n, regresi), "01_benchmark_waktu")
    viz.simpan(viz.gambar_keluarga_query(
        [(r.keluarga, r.rasio) for r in ring.itertuples()],
        f"Median rasio waktu SQLite / Neo4j dari {n} run terpisah (Neo4j dinyalakan ulang tiap run); hasil identik pada "
        f"{int(ring['hasil_sama'].sum())} dari {len(ring)} pasangan."), "10_perbandingan_keluarga_query")
    if any(kurva):
        viz.simpan(viz.gambar_pemanasan([k for k in kurva if k]), "11_pemanasan_jvm")
    hub = skala.sort_values("jumlah_path", ascending=False).groupby("n_edge").head(1)
    users_hub = int(khop[khop["k"] == 3].sort_values("jumlah_path", ascending=False).iloc[0]["user_id"])
    nyata = khop[(khop["k"] == 3) & (khop["user_id"] == users_hub)].assign(n_edge=int(lain_pertama["profil_graf"]["edge"]))
    viz.simpan(viz.gambar_skala(pd.concat([nyata, hub], ignore_index=True)), "12_skala_graf")
    viz.simpan(viz.gambar_strategi_hybrid(strategi), "13_strategi_hybrid")
    viz.simpan(viz.gambar_lintas_batas(lintas), "14_biaya_lintas_batas")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(f"Gabungan {n} run: {', '.join(runs)}")
    print("Tes per run:", ringkas_tes)
    kolom = ["keluarga", "sqlite_ms", "neo4j_ms", "rasio", "rasio_min", "rasio_maks", "pemenang", "pemenang_konsisten", "hasil_sama"]
    ring["rasio_min"] = per_run.groupby("keluarga", sort=False)["rasio"].min().reindex(ring["keluarga"]).to_numpy()
    ring["rasio_maks"] = per_run.groupby("keluarga", sort=False)["rasio"].max().reindex(ring["keluarga"]).to_numpy()
    simpan(ring, "ringkasan")
    print(ring[kolom].round(3).to_string(index=False))
    print("\nBiaya per path (us), data gabungan:", {k: round(v["b_mikrodetik_per_path"], 3) for k, v in regresi.items()},
          "| antar-run:", {k: [round(x, 3) for x in v] for k, v in sebaran.items()})
    print("\nVonis hipotesis:")
    print(vonis[["hipotesis", "hasil"]].to_string(index=False))
    print("\nJawaban:")
    for baris in jawaban:
        print(" -", baris)


if __name__ == "__main__":
    main()
