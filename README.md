# Hybrid Database: SQLite + Neo4j (Pokec Social Network)

Eksperimen yang menjalankan **database relasional (SQLite)** dan **graph database (Neo4j Desktop, lokal)**
*berdampingan* dan saling melengkapi, dengan Python sebagai penghubung. Bukan migrasi satu arah:
masing-masing database menyimpan apa yang paling cocok untuknya.

Data: **Pokec Social Network** dari SNAP Stanford (jejaring sosial asli Slovakia, bukan data sintetis):
<https://snap.stanford.edu/data/soc-Pokec.html>

| Database | Menyimpan | Kenapa di sini |
|---|---|---|
| **SQLite** (`data/pokec.db`) | Atribut/profil: tabel `users` (18 kolom), tabel `hobbies` (user ↔ hobi) | Data tabular, mudah difilter dan diagregasi dengan SQL |
| **Neo4j** (Desktop, lokal) | Struktur jaringan: `(:User)-[:FRIEND]->(:User)`, `(:User)-[:HAS_HOBBY]->(:Hobby)` | Traversal beberapa hop (teman dari teman) adalah operasi native graph |
| **Python** (`scripts/04`) | Menggabungkan keduanya | Neo4j menjawab "siapa terhubung dengan siapa", SQLite menjawab "siapa mereka" |

```
 soc-pokec-*.txt.gz ──[01 subsampling]──> data/users_sample.csv   data/edges_sample.csv
  (±550 MB, 1,6 juta user)                        │                        │
                                         [02] atribut                [03] relasi
                                                  ▼                        ▼
                                          SQLite  pokec.db         Neo4j Desktop (lokal)
                                          users, hobbies           User, Hobby, FRIEND, HAS_HOBBY
                                                  ▲                        ▲
                                                  └──[04 Python menggabungkan hasil]──┘
```

Hasil nyata dari satu kali menjalankan seluruh proyek ada di **[HASIL.md](HASIL.md)**.

> **Offline.** Satu-satunya langkah yang butuh internet adalah mengunduh dataset di script 01.
> Setelah itu semuanya berjalan lokal. Koneksi Neo4j hanya diizinkan ke `localhost`
> (URI cloud/AuraDB langsung ditolak oleh kode), dan Neo4j tidak pernah dijalankan dari Python:
> Anda yang menekan **Start** di Neo4j Desktop.

## Struktur folder

```
data/        dataset .gz, CSV hasil sampling, pokec.db   (seluruh isinya di-.gitignore)
scripts/     01_subsample_data.py  02_load_sqlite.py  03_sync_to_neo4j.py  04_hybrid_queries.py  common.py
             (khusus notebook: neo4j_lokal.py = nyalakan/cek/matikan Neo4j, uji_hybrid.py = pencatat tes + jawaban kunci,
              eksperimen.py = pengukuran dan perbandingan SQLite vs Neo4j, visualisasi.py = gambar,
              rangkum_run.py = gabungkan beberapa run notebook 1 menjadi median antar-run)
queries/     query Cypher/SQL yang dipakai script 04 dan notebook (bisa ditempel langsung ke Neo4j Browser)
notebooks/   1_tes_semua.ipynb (apakah graf dan relasional bisa digabung? tes + perbandingan)  2_lihat_graf_di_browser.ipynb (graf interaktif)
docs/        visualisasi/  (PNG hasil notebook: gambar graf, skema SQLite, grafik perbandingan)
             hasil/        (angka mentah hasil notebook 1: CSV/JSON; run1-3 dan gabungan = bahan laporan)
requirements.txt   requirements-notebook.txt   .env.example   HASIL.md
```

## 1. Persiapan Python (environment baru)

Butuh Python 3.10+. Sebaiknya pakai environment tersendiri supaya environment lain (mis. `base`) tidak tercampur.
Dari folder proyek, dengan **conda**:

```powershell
conda create -n hybrid-db python=3.13
conda activate hybrid-db
pip install -r requirements-notebook.txt   # script + notebook. Hanya script? pakai requirements.txt
python -m ipykernel install --user --name hybrid-db --display-name "Python (hybrid-db)"   # agar terlihat di Jupyter
```

Tanpa conda, pakai venv:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt       # pandas, neo4j (driver resmi), python-dotenv
```

`requirements.txt` cukup untuk menjalankan script 01-04; `requirements-notebook.txt` menambahkan JupyterLab dan
matplotlib untuk kedua notebook.

**Memakai PyCharm?** Set interpreter proyek ke environment tadi, kalau tidak script akan berhenti dengan pesan
"Modul Python '...' belum terpasang di interpreter yang sedang dipakai" (pesan itu menyebut interpreter mana yang
sedang jalan): *Settings* → *Project: GraphDatabaseSQLHybrid* → *Python Interpreter* → *Add Interpreter* →
*Add Local Interpreter* → *Conda Environment* → *Use existing environment* → pilih `hybrid-db`
(`...\Miniconda\envs\hybrid-db\python.exe`). Notebook di PyCharm Professional memakai interpreter proyek yang sama.

## 2. Instalasi Neo4j Desktop (hanya perlu untuk script 03 dan 04)

> Nama menu/tombol bisa sedikit berbeda antar versi Neo4j Desktop. Intinya sama: buat satu DBMS lokal,
> beri password, lalu Start.

1. **Unduh dan pasang** Neo4j Desktop dari <https://neo4j.com/download/>.
2. **Buat DBMS lokal baru** (mis. tombol *Create instance* / *New → Local DBMS*). Beri nama bebas
   (mis. `pokec-hybrid`), pilih versi **Neo4j 5.x atau lebih baru** (script diuji pada 5.26 LTS).
3. **Set password** untuk user `neo4j` saat membuat DBMS tersebut, lalu **catat**. Anda memerlukannya di langkah 4.
4. Klik **Start** pada DBMS itu dan tunggu statusnya **Running**. Biarkan Neo4j Desktop terbuka selama
   menjalankan script 03 dan 04.
5. Cek port Bolt di detail DBMS (default **7687**). Kalau Anda punya beberapa DBMS lokal, portnya bisa lain.

Lalu buat file `.env` dari template dan isi password tadi:

```powershell
copy .env.example .env
notepad .env
```

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password DBMS Anda>
```

`.env` sudah ada di `.gitignore`, jadi password tidak ikut ter-commit.

### Alternatif: Neo4j Community tanpa Desktop

Kode proyek ini jalan di Neo4j lokal mana pun lewat `localhost`. Alternatif tanpa Desktop (diuji dengan
Neo4j Community 5.26, butuh Java 17):

1. Ekstrak zip Neo4j Community 5.26.x untuk Windows ke folder tetap, mis. `D:\Softwares\neo4j-community-5.26.31`.
2. Tambahkan ke `conf/neo4j.conf` agar hanya menerima koneksi dari komputer ini dan tanpa pelaporan penggunaan:
   ```
   server.default_listen_address=localhost
   server.bolt.listen_address=localhost:7687
   server.http.listen_address=localhost:7474
   dbms.usage_report.enabled=false
   ```
3. Sebelum start pertama, set password: `bin\neo4j-admin.bat dbms set-initial-password <password>`
   (jika gagal, **jangan** lanjut: perbaiki dulu pesan errornya, mis. setting yang salah ketik di `neo4j.conf`).
4. Nyalakan: `bin\neo4j.bat console`. Jendela itu harus tetap terbuka selama dipakai; **Ctrl+C** untuk berhenti.
   Tanpa mengetik: simpan file `Mulai-Neo4j.bat` di folder Neo4j berisi `cd /d "<folder Neo4j>"`, lalu
   `call bin\neo4j.bat console`, lalu `pause`, dan klik dua kali (atau buat pintasannya di Desktop).
5. Isi `.env` dengan password yang sama. Jangan menyalakan ini bersamaan dengan Neo4j Desktop di port 7687.

## 3. Menjalankan script (berurutan)

```powershell
python scripts/01_subsample_data.py     # unduh (±550 MB, hanya sekali) + subsampling -> CSV. Tidak butuh Neo4j.
python scripts/02_load_sqlite.py        # CSV -> data/pokec.db.                      Tidak butuh Neo4j.
# >>> sekarang Start DBMS di Neo4j Desktop <<<
python scripts/03_sync_to_neo4j.py      # CSV -> graph di Neo4j.
python scripts/04_hybrid_queries.py     # demo query hybrid + benchmark SQL vs Cypher.
```

Seluruh rangkaian makan waktu sekitar satu menit di mesin pengembangan (di luar waktu unduhan).

| Script | Fungsi | Opsi berguna |
|---|---|---|
| `01_subsample_data.py` | Unduh dataset, pilih satu region, ambil induced subgraph, tulis `users_sample.csv` + `edges_sample.csv`, cetak ringkasan | `--region "zilinsky kraj, zilina"`, `--min-users/--max-users`, `--min-completion 50` |
| `02_load_sqlite.py` | Buat `pokec.db` (tabel `users`, `hobbies`), muat data, validasi jumlah baris + pemakaian index | – |
| `03_sync_to_neo4j.py` | Buat constraint unique, lalu `UNWIND` + `MERGE` per batch untuk `User`, `Hobby`, `FRIEND`, `HAS_HOBBY` | `--batch-size 1000`, `--reset` |
| `04_hybrid_queries.py` | Menjalankan 4 fungsi hybrid + 1 bonus | `--user-id`, `--hobby`, `--limit`, `--ulangi`, `--pemanasan`, `--skip-benchmark` |

Script 03 aman dijalankan ulang (memakai `MERGE`). Kalau Anda **mengganti hasil sampling**, jalankan ulang
02 dan `03 --reset` (menghapus hanya node berlabel `User` dan `Hobby`, data lain di DBMS yang sama tidak disentuh).

Fungsi-fungsi di script 04 juga bisa dipanggil dari Python/notebook:
`rekomendasi_teman(user_id)`, `cari_komunitas_hobi(hobby_name)`, `user_paling_terhubung(limit=10)`,
`bandingkan_performa_query()`, dan bonus `rekomendasi_hobi_sama(user_id)`. Tiap fungsi punya docstring yang
menjelaskan database mana yang dipakai dan kenapa pekerjaannya dibagi begitu.

Contoh: komunitas hobi yang lebih "niche" (hobi terpopuler menghasilkan satu klaster raksasa):

```powershell
python scripts/04_hybrid_queries.py --hobby chovatelstvo --skip-benchmark
```

### Dua notebook (opsional)

| Notebook | Untuk | Cara pakai |
|---|---|---|
| [1_tes_semua.ipynb](notebooks/1_tes_semua.ipynb) | Menjawab **"bisakah graph database dikombinasikan dengan relational database biasa?"**: tes kebenaran + perbandingan SQLite vs Neo4j yang diukur | **Run All.** Neo4j menyala sendiri, semua tes dan pengukuran jalan, lalu Neo4j mati. Lama sekitar 1,5-2 menit. |
| [2_lihat_graf_di_browser.ipynb](notebooks/2_lihat_graf_di_browser.ipynb) | Menjelajahi graf secara **interaktif di Neo4j Browser** | **Bukan Run All.** Hanya dua sel: jalankan sel 1 (start), klik tautan yang muncul lalu bermain-main di browser, jalankan sel 2 (stop). |

Pilih kernel **Python (hybrid-db)** (di PyCharm Professional: interpreter proyek = `hybrid-db`), atau pakai `jupyter lab notebooks/`.

**Notebook 1** disusun menurut lima pertanyaan penelitian (RQ1-RQ5, dijelaskan di laporan) dan menyimpulkan di sel terakhir:
*berapa tes LULUS/GAGAL*, *lima hipotesis (H1-H5) didukung atau tidak*, dan *jawaban untuk pertanyaan "bisakah dikombinasikan?"*
yang dihitung dari angka hasil pengukuran (bukan teks tetap). Isinya (40 tes; 41 bila graf masih kosong):

| Kelompok | Yang diuji | Acuan pustaka (open access) |
|---|---|---|
| 0 Persiapan | prasyarat, Neo4j menyala, koneksi, profil struktur sampel dibanding seluruh Pokec | Takac dan Zabovsky (2012) lewat halaman SNAP |
| 1 Konsistensi | jumlah dan **himpunan** user, edge, user-hobi sama persis di Neo4j dan SQLite; atribut yang diduplikasi (gender, age, region) sinkron | Fowler (2011) |
| 2 Sinkronisasi | menjalankan ulang script 03 tidak menggandakan data; 3 penyimpangan (drift) disuntik, terdeteksi persis, lalu diperbaiki dari SQLite | Yuan dkk. (2023) |
| 3 Kebenaran | 5 fungsi hybrid dicocokkan dengan **jawaban yang dihitung ulang dengan Python murni dari CSV** (termasuk hub, user tanpa teman, hobi yang tidak ada), dan kolom profil SQLite yang digabungkan | Backstrom dan Leskovec (2011) |
| 4 Kesetaraan dan kinerja | **pertanyaan yang sama dijawab di SQLite dan di Neo4j, hasilnya harus identik** sebelum waktunya dihitung: pencarian titik, agregasi, rekomendasi teman, teman tepat 1-4 relasi (empat cara), jalur terpendek, filter atribut dengan tiga strategi (semua SQL / semua Neo4j / hybrid) | Cheng dkk. (2019); Hassan dkk. (2018); Erling dkk. (2015, LDBC SNB); Francis dkk. (2018); Georges dkk. (2007) |
| 5 Biaya | waktu lintas batas, ukuran di disk, data ganda | Fowler (2011) |
| 6 Skala | graf sintetis berpola jaringan sosial yang dimuat sementara (10 ribu dan 40 ribu user, sampai ±544 ribu edge) | Barabasi dan Albert (1999) |
| 8 Gambar | 14 gambar di `docs/visualisasi/` berhasil dibuat | |

Satu tes yang error dicatat GAGAL tanpa menghentikan notebook. Neo4j dimatikan di akhir **hanya kalau notebook ini yang menyalakannya**.
Semua angka juga disimpan ke [docs/hasil/](docs/hasil/) (CSV/JSON). Karena JVM Neo4j berbeda tiap kali dinyalakan, laporan memakai
**tiga run terpisah** (Neo4j dinyalakan ulang tiap run): jalankan notebook dengan variabel lingkungan `HASIL_SUBDIR=run1` (lalu `run2`,
`run3`), kemudian `python scripts/rangkum_run.py run1 run2 run3` menghasilkan median antar-run di `docs/hasil/gabungan/` dan menggambar
ulang grafiknya.

**Notebook 2** mencetak tautan `http://localhost:7474`, data login yang perlu diisi di form Neo4j Browser (password diambil dari `.env`,
tidak ditampilkan), dan beberapa query siap tempel. Jangan menutup atau me-restart kernel selama menjelajah, karena Neo4j ikut berhenti.

Menyalakan Neo4j dari notebook memakai [scripts/neo4j_lokal.py](scripts/neo4j_lokal.py) dan butuh `NEO4J_HOME=<folder Neo4j
Community>` di `.env` (opsional; lihat `.env.example`) serta Java 17. Ini **hanya berlaku di notebook**: script 01-04 tetap tidak
pernah menyalakan Neo4j sendiri. Neo4j yang dinyalakan notebook berjalan di latar belakang tanpa jendela dan, dalam pengamatan lewat
`nbconvert`, ikut berhenti saat kernel dimatikan. Kalau Anda memakai Neo4j Desktop, nyalakan lewat tombol Start seperti biasa; sel
"nyalakan" di notebook akan melihatnya sudah hidup dan tidak melakukan apa-apa.

### Di mana visualisasinya?

Semua gambar dibuat oleh `1_tes_semua.ipynb` (disimpan ulang setiap kali dijalankan) sebagai PNG di
[docs/visualisasi/](docs/visualisasi/), jadi bisa dibuka tanpa menjalankan apa pun:

| Gambar | Isi |
|---|---|
| [02_model_graf_neo4j.png](docs/visualisasi/02_model_graf_neo4j.png) | **Graph:** node `User`/`Hobby`, relasi `FRIEND`/`HAS_HOBBY`, properti, dan jumlahnya |
| [04_jaringan_user_demo.png](docs/visualisasi/04_jaringan_user_demo.png) | **Graph:** jaringan satu user: teman langsung dan kandidat rekomendasi |
| [05_klaster_hobi.png](docs/visualisasi/05_klaster_hobi.png) | **Graph:** satu klaster hobi (bentuk dari Neo4j, warna gender dari SQLite) |
| [06_distribusi_derajat.png](docs/visualisasi/06_distribusi_derajat.png) | **Graph:** sebaran jumlah teman per user dan hub terbesar |
| [03_skema_sqlite.png](docs/visualisasi/03_skema_sqlite.png) | **Relasional:** tabel, kolom, PK/FK, jumlah baris |
| [07_hobi_terpopuler.png](docs/visualisasi/07_hobi_terpopuler.png), [08_sebaran_umur.png](docs/visualisasi/08_sebaran_umur.png), [09_pendidikan.png](docs/visualisasi/09_pendidikan.png) | **Relasional:** grafik dari query SQL atas tabel `users` dan `hobbies` |
| [01_benchmark_waktu.png](docs/visualisasi/01_benchmark_waktu.png) | Waktu "tepat k relasi" menurut jumlah path: dua pasangan setara (semua path; himpunan unik) |
| [10_perbandingan_keluarga_query.png](docs/visualisasi/10_perbandingan_keluarga_query.png) | Siapa lebih cepat untuk tiap jenis pertanyaan (rasio waktu SQLite / Neo4j) |
| [11_pemanasan_jvm.png](docs/visualisasi/11_pemanasan_jvm.png) | Query yang sama di Neo4j yang baru menyala: panggilan pertama vs stabil |
| [12_skala_graf.png](docs/visualisasi/12_skala_graf.png) | Waktu hub pada graf yang makin besar (sampel Pokec dan graf sintetis) |
| [13_strategi_hybrid.png](docs/visualisasi/13_strategi_hybrid.png) | Tiga strategi "teman dari teman + filter atribut": semua SQL, semua Neo4j, hybrid |
| [14_biaya_lintas_batas.png](docs/visualisasi/14_biaya_lintas_batas.png) | Biaya mengambil atribut N user dari SQLite vs dari node Neo4j |

Gambar di atas statis. Untuk menjelajahi graf secara **interaktif** (geser, klik node, perluas tetangga), pakai
`2_lihat_graf_di_browser.ipynb` (atau buka **Neo4j Browser** di <http://localhost:7474> sendiri setelah Neo4j menyala),
mis. dengan query `MATCH (u:User)-[f:FRIEND]->(v:User) RETURN u, f, v LIMIT 100`. Server Neo4j-nya sendiri hanya lokal. **Catatan offline untuk
Neo4j Browser:** aplikasi web ini disajikan dari server lokal Anda, tetapi di kodenya ada rujukan ke layanan analitik/pelacakan (Sentry,
Segment, Google tag) dan layarnya menampilkan banner yang mengarah ke Aura (cloud). Kemunculan nama itu di kode **belum membuktikan**
ada permintaan yang benar-benar dikirim, dan saya tidak memeriksa lalu lintas jaringan browser. Kalau offline-nya harus ketat, putuskan
koneksi internet komputer selama menjelajah (Browser berjalan dari server lokal sehingga seharusnya tetap bisa dipakai; belum saya uji),
jangan klik banner Aura, dan periksa menu pengaturan Browser untuk opsi pengiriman data penggunaan. Tabel SQLite bisa dilihat lewat PyCharm Professional
(tool window *Database*, sumber data SQLite ke `data/pokec.db`; IDE mungkin mengunduh driver JDBC sekali) atau DB Browser for SQLite.
Kode penggambarnya ada di [scripts/visualisasi.py](scripts/visualisasi.py).

Script 01-03 sengaja tetap berupa `.py` (langkah batch berurutan dengan opsi CLI dan pesan error yang jelas),
sedangkan notebook dipakai untuk menjelajahi hasil query. Karena nama file `04_hybrid_queries.py` diawali angka,
notebook memuatnya lewat `importlib` (lihat sel pertama).

## 4. Keputusan desain dan asumsi

**Subsampling (script 01).** Dataset penuh (1.632.803 user, 30.622.564 edge) terlalu besar untuk laptop.
Script mengambil *satu region*: kandidatnya region berukuran 3.000-8.000 user (ada 53 dari 187 region), lalu dipilih
yang **paling rapat** (rata-rata teman sesama region terbanyak) supaya traversal multi-hop bermakna. Hanya edge yang
kedua ujungnya ada di region itu yang dipakai (induced subgraph). Pada data asli terpilih
`zilinsky kraj, trstena`: 4.505 user dan 72.004 edge. Filter kualitas `--min-completion` tersedia tetapi
default-nya mati: menyaring user juga membuang edge secara kuadratik dan membuat graph terlalu jarang.

**Format data asli yang perlu diketahui.** Setiap baris profil punya 60 field, sedangkan README SNAP hanya
mendaftar 59 nama kolom: field ke-60 selalu kosong (ada tab di ujung baris) dan diabaikan. Nilai kosong ditulis
sebagai string `null`. Teks bebas mengandung tanda kutip `"`, jadi file dibaca tanpa quoting. Isi data berbahasa
Slovakia tanpa diakritik.

**Pembersihan.** `null` → NULL; teks diseragamkan (huruf kecil, spasi dirapikan); `last_login` dan `registration`
tanpa `.0` di ujung; `gender` 1 = pria, 0 = wanita (menurut README SNAP). **Umur** hanya dianggap valid pada
10-90: nilai `0` berarti "tidak diisi", sedangkan ±13 ribu user berumur 1-9 dan ±1,6 ribu berumur 100+
jelas isian asal-asalan, semuanya jadi NULL.

**Kolom SQLite.** 18 kolom: semua yang Anda sebut (`user_id, gender, age, region, completion_percentage,
last_login, registration, completed_level_of_education, relation_to_smoking, relation_to_alcohol, body_type,
eye_color, hair_color, favourite_color`) ditambah `public`, `hair_type`, `marital_status`, `sign_in_zodiac`
(kolom lain yang paling banyak terisi dan paling bersih). Kolom `body` ("185 cm, 90 kg") tidak dipakai karena
hanya ±46% barisnya mengikuti pola yang bisa di-parse. Kolom kategori seperti pendidikan dan warna mata di data
asli memang campuran pilihan baku + teks bebas; nilainya disimpan apa adanya.

**Hobi.** Kolom `hobbies` dipecah per koma. Data asli berisi 33 pilihan baku (`pocuvanie hudby`, `sportovanie`, ...)
ditambah teks bebas buatan pengguna: ±224 ribu nilai hobi berbeda secara total, ±93% di antaranya hanya muncul
sekali. Hobi yang dimiliki **kurang dari 3 user**
di sampel dibuang (tidak berguna untuk "hobi yang sama"). Aturan ini ada di satu fungsi (`build_hobby_rows`) yang
dipakai bersama oleh 02 dan 03, sehingga tabel `hobbies` di SQLite dan node `Hobby` di Neo4j pasti identik.

**Arah pertemanan.** `FRIEND` bersifat directed seperti data asli (`3 5` = user 3 menandai user 5 sebagai teman);
±71% edge di sampel timbal-balik. Di `rekomendasi_teman`, penelusuran mengikuti arah `FRIEND`, tetapi "belum berteman
langsung" berarti *tidak ada relasi ke arah mana pun*. Degree centrality = jumlah relasi masuk + keluar
(pertemanan timbal-balik dihitung dua relasi).

**Benchmark "tepat k relasi" (script 04 dan notebook 1).** Pertanyaannya: berapa user unik yang bisa dicapai lewat *tepat* k relasi
`FRIEND` (selain diri sendiri)?
- SQLite: tabel `friendships` (salinan edge, dibuat hanya untuk perbandingan) dengan `PRIMARY KEY (user_id_1, user_id_2)` sehingga
  tiap JOIN memakai index. Tanpa index perbandingan ini tidak adil.
- Cypher memakai aturan "satu relasi tidak boleh dipakai dua kali dalam satu path" (Francis dkk., 2018); SQL meniru aturan itu
  (`NOT (f3... = f1...)`) supaya hasil keduanya sama persis. Script memverifikasi **jumlah + checksum** hasil di kedua sisi.
- **Dua pasangan yang setara, bukan satu.** (1) *Menyusuri semua path*: SQL JOIN berulang vs Cypher yang juga menghitung path
  (`count(p)`); kerjanya sama, dan hasilnya mirip (±0,42 µs per path di SQLite, ±0,34 µs di Neo4j). (2) *Hanya himpunan user unik*:
  SQL `DISTINCT` per level vs Cypher tanpa `count(p)`; di sini Neo4j memakai `VarLengthExpand(Pruning)` (memangkas, terlihat di
  `EXPLAIN`), sehingga jauh lebih cepat daripada JOIN berulang, tetapi hanya sekitar 1,1-1,4× lebih cepat daripada SQL yang ditulis
  dengan `DISTINCT`. Jadi selisih 8× yang tampak di benchmark awal sebagian besar adalah selisih *cara menulis query*, bukan selisih
  penyimpanan.
- Sebelum diukur ada **pemanasan 3 detik** (`--pemanasan`): JVM Neo4j yang baru menyala itu dingin (query pertama ±460 ms, stabil
  ±16 ms). Lalu tiap user diukur beberapa kali bergantian, diambil median; user uji mencakup yang paling banyak teman sampai yang
  sedang. Waktu Neo4j dihitung end-to-end dari Python (termasuk Bolt), sama seperti SQLite.
- Pengukuran memakai `time.perf_counter()`, bukan `time.time()`: di Windows dengan Python 3.12 ke bawah resolusi
  `time.time()` hanya ±15 ms, sehingga query 2-3 ms akan terbaca 0.
- Perbandingan SQLite vs Neo4j juga mencampur dua hal: **mesin** dan **cara dipanggil**. SQLite berjalan di dalam proses Python,
  sedangkan Neo4j dipanggil lewat jaringan lokal (Bolt) dengan biaya tetap ±0,85 ms per panggilan. Karena itu pencarian satu baris
  SQLite jauh lebih cepat. Kolom `neo4j_server_ms` memisahkan waktu di server.

**Graf sintetis (uji skala).** Dimuat sementara ke Neo4j dengan label `Syn` (relasi `S_FRIEND`) dan ke SQLite basis data memori, lalu
dihapus. Data asli (`User`, `Hobby`) tidak disentuh; notebook memeriksanya. File penyimpanan Neo4j tidak menyusut setelah data
dihapus (wajar bagi basis data), dan log transaksi diatur `db.tx_log.rotation.retention_policy=keep_none` di `neo4j.conf` supaya tidak
menumpuk ratusan MB.

## 5. Query di folder `queries/`

Script 04 membaca query dari sini (satu sumber, tanpa salinan di kode), jadi Anda bisa menempelkannya ke Neo4j
Browser. Parameter diset dengan `:param user_id => 1804` (komentar di tiap file memberi contoh).

| File | Dipakai oleh |
|---|---|
| `rekomendasi_teman.cypher` | `rekomendasi_teman()` |
| `komunitas_hobi_anggota.cypher`, `komunitas_hobi_koneksi.cypher` | `cari_komunitas_hobi()` |
| `user_paling_terhubung.cypher` | `user_paling_terhubung()` (dan pemilihan user uji) |
| `teman_3_level.cypher` / `teman_3_level.sql` | `bandingkan_performa_query()` (dua pesaing utama) |
| `teman_3_level_dioptimalkan.sql`, `teman_3_level_jumlah_path.sql` | benchmark (pembanding bonus dan penjelasan) |
| `rekomendasi_hobi_sama.cypher` | `rekomendasi_hobi_sama()` (bonus) |
| `teman_langsung.cypher`, `relasi_antar_user.cypher`, `model_graf_properti.cypher`, `model_graf_jumlah.cypher` | gambar graf di notebook |
| `teman_k_level.cypher`, `teman_k_level_unik.cypher` | notebook 1: tepat k relasi (`__K__` diganti angka); versi pertama menghitung path, versi kedua hanya himpunan unik |
| `pencarian_titik`, `agregasi_gender`, `agregasi_derajat`, `rekomendasi_teman` (`.sql`), `rekomendasi_teman_inti.cypher`, `jalur_terpendek`, `fof_filter` (`.sql`/`.cypher`), `fof_ids.cypher` | notebook 1: pasangan SQL/Cypher untuk pertanyaan yang sama |
| `atribut_node.cypher`, `relasi_semua.cypher`, `hobi_semua.cypher` | notebook 1: membandingkan isi Neo4j dengan SQLite |

## 6. Kamus kecil (data berbahasa Slovakia)

| Slovakia | Arti | | Slovakia | Arti |
|---|---|---|---|---|
| priatelia | teman | | cestovanie | bepergian |
| pocuvanie hudby | mendengarkan musik | | chovatelstvo | memelihara/beternak hewan |
| sportovanie | berolahraga | | hackovanie | hacking |
| pozeranie filmov | menonton film | | zakladne | pendidikan dasar |
| spanie | tidur | | stredoskolske | pendidikan menengah |
| pc hry | game PC | | vysokoskolske | perguruan tinggi |
| tancovanie | menari | | slobodny(a) | lajang |

(Terjemahan bebas untuk membantu membaca output.)

## 7. Troubleshooting

| Pesan / gejala | Penyebab dan solusi |
|---|---|
| `Tidak bisa terhubung ke Neo4j di bolt://localhost:7687` | DBMS belum di-Start (status harus *Running*), atau port-nya bukan 7687: cek detail DBMS lalu ubah `NEO4J_URI` di `.env`. |
| `Login ... ditolak` | `NEO4J_USER` / `NEO4J_PASSWORD` di `.env` tidak sama dengan password DBMS. |
| `NEO4J_PASSWORD belum diisi` | `.env` belum dibuat atau masih berisi nilai template. |
| `NEO4J_URI=... ditolak` | Host bukan localhost. Proyek ini sengaja hanya mau terhubung ke Neo4j lokal. |
| `Graph di Neo4j masih kosong` | Jalankan `03_sync_to_neo4j.py` dulu. |
| Jumlah di ringkasan 03 `TIDAK COCOK` | Graph berisi sisa sampling lama: jalankan `03_sync_to_neo4j.py --reset`. |
| `pokec.db sedang dibuka program lain` | Tutup DB Browser/IDE yang membuka file itu, lalu jalankan 02 lagi. |
| Unduhan di 01 gagal | Simpan manual `soc-pokec-profiles.txt.gz` dan `soc-pokec-relationships.txt.gz` dari halaman SNAP ke folder `data/`. |
| `File .gz rusak atau tidak lengkap` | Hapus file di `data/` yang bersangkutan lalu jalankan 01 lagi. |
| `Modul Python '...' belum terpasang di interpreter yang sedang dipakai` | IDE/terminal memakai interpreter lain. Pilih environment `hybrid-db` (lihat bagian 1) atau jalankan `pip install -r requirements.txt` di environment yang dipakai. |
| Error sintaks `CREATE CONSTRAINT ... REQUIRE` | Versi Neo4j di bawah 5.0. Buat DBMS baru dengan Neo4j 5.x atau lebih baru. |
