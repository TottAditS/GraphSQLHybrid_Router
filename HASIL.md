# HASIL - Eksekusi nyata proyek Hybrid SQLite + Neo4j

Dokumen ini berisi keluaran **asli** dari menjalankan `scripts/01` sampai `04` berurutan. Semua blok kode adalah
salinan apa adanya dari terminal, tidak diketik ulang. Angka di blok kode memakai format Python (koma = pemisah
ribuan); teks di luar blok memakai format Indonesia.

## Lingkungan dan catatan penting

Dokumen ini punya dua kelompok hasil, dari dua server Neo4j yang berbeda:

- **Bagian 1-4** (keluaran script 01-04): diperoleh saat pengembangan dari server Neo4j Community 5.26.31 sementara di
  `bolt://localhost:7699` (hanya loopback).
- **Bagian 5** (notebook 1, tes dan perbandingan lengkap): diperoleh dari Neo4j Community 5.26.31 **yang sama dengan yang dipakai
  proyek ini sehari-hari** (`NEO4J_HOME` di `.env`, port 7687), dinyalakan dan dimatikan oleh notebook itu sendiri.

| | |
|---|---|
| Tanggal | 3 Oktober 2026 |
| Mesin | Windows 11 Pro, Intel Core i7-12700KF (20 thread logis), RAM 31,8 GB, SSD NVMe |
| Python dan pustaka | environment conda `hybrid-db`: Python 3.13.16, pandas 3.0.6, neo4j (driver) 6.3.1, python-dotenv 1.2.4 |
| Server Neo4j | Neo4j Kernel 5.26.31 community (Neo4j Community, bukan Desktop) |
| SQLite | 3.53.4 (modul `sqlite3` bawaan Python) |

> **Penting: ini bukan Neo4j Desktop.** Neo4j Desktop adalah aplikasi GUI yang tidak bisa dioperasikan dari lingkungan
> tempat proyek ini dibuat, jadi semua hasil diperoleh dari server Neo4j Community 5.26.31. Cypher, skema, dan driver-nya sama
> dengan yang akan Anda pakai di Desktop, tetapi **waktu eksekusi di mesin Anda akan berbeda**: anggaplah angka waktu di sini sebagai
> gambaran, bukan patokan.

Pemeriksaan tambahan yang dilakukan (dengan skrip sementara di luar proyek):
- Keluaran fungsi a, b, c, bonus, dan hitungan benchmark dihitung ulang dengan **Python murni dari CSV**
  (tanpa Neo4j/Cypher) untuk beberapa user dan hobi. Semuanya cocok.
- Seluruh script dijalankan juga dengan pustaka terlama yang diizinkan `requirements.txt`
  (pandas 2.3.3, neo4j 5.28.6, python-dotenv 1.0.1): hasilnya sama, dan `users_sample.csv` serta
  `edges_sample.csv` identik byte-per-byte dengan hasil pandas 3.0.
- `notebooks/1_tes_semua.ipynb` (versi lengkap, lihat bagian 5) dijalankan **tiga kali dari kondisi Neo4j mati** lewat `nbconvert`
  dengan kernel `hybrid-db`: **40 tes LULUS, 0 GAGAL di tiap run**, ±100 detik per run.
  `notebooks/2_lihat_graf_di_browser.ipynb` diuji dengan kernel hidup: sel 1 menyalakan Neo4j, Neo4j Browser
  menjawab HTTP 200, sel 2 mematikannya.
- Seluruh rangkaian 01 → 04 (data sudah terunduh) berjalan sekitar satu menit.

## 1. Data yang diproses

| | Jumlah |
|---|---|
| Dataset asli (SNAP) | 1.632.803 user, 30.622.564 edge (directed) |
| Region di dataset / region berukuran 3.000-8.000 user | 187 / 53 |
| Region terpilih (rata-rata teman sesama region tertinggi: 15,98) | `zilinsky kraj, trstena` |
| **User dalam sampel** | **4.505** (0,28% dari total) |
| **Edge `FRIEND` dalam sampel** (induced subgraph) | **72.004** (0,24% dari total) |
| Pasangan user-hobi / hobi berbeda (setelah disaring) | 19.512 / 60 (2.513 user punya hobi) |
| Out-degree rata-rata / median / maksimum | 16,0 / 10 / 185 |
| User tanpa koneksi sama sekali | 502 (11,1%) |
| Edge timbal-balik (A→B yang juga punya B→A) | 71,1% |
| Gender | pria 2.287 (50,8%), wanita 2.218 (49,2%) |
| Umur valid (10-90) | 3.064 user (68,0%), median 20 tahun |
| **SQLite** `pokec.db` | `users` 4.505 baris, `hobbies` 19.512 baris |
| **Neo4j** | 4.565 node (4.505 `User` + 60 `Hobby`), 91.516 relasi (72.004 `FRIEND` + 19.512 `HAS_HOBBY`) |

Jumlah di SQLite dan Neo4j sama dengan isi CSV (script 02 dan 03 memeriksanya sendiri dan mencetak `OK`).

## 2. Keluaran script 01-03

### 01_subsample_data.py

```
=== [1/5] Memeriksa dataset di data/ ===
  soc-pokec-profiles.txt.gz: sudah ada (436 MB), unduhan dilewati
  soc-pokec-relationships.txt.gz: sudah ada (132 MB), unduhan dilewati

[2/5] Membaca user_id, completion_percentage, region dari semua profil ...
      1,632,803 profil dibaca (8 dtk); 187 region; 53 region berukuran 3,000-8,000 user

[3/5] Membaca ±30,6 juta edge, menyaring edge di dalam 53 region kandidat ...
      30,622,564 edge dibaca (6 dtk); 0 self-loop dibuang; 1,792,065 edge jatuh di dalam region kandidat

[4/5] Region terpilih: zilinsky kraj, trstena

[5/5] Mengambil profil lengkap user terpilih + menulis CSV ...
      ditulis: data\users_sample.csv (4,505 baris), data\edges_sample.csv (72,004 baris)

=== RINGKASAN HASIL SAMPLING ===
Region terpilih      : zilinsky kraj, trstena
Jumlah user          : 4,505
Jumlah edge (FRIEND) : 72,004   (directed, induced subgraph)
Rata-rata teman/user : 16.0 (out-degree)
Out-degree           : min 0 | median 10 | maks 185
User tanpa koneksi   : 502 (11.1%)
Edge timbal-balik    : 71.1% (A->B yang juga punya B->A)

=== Distribusi gender (1 = pria, 0 = wanita) ===
  pria       : 2,287 (50.8%)
  wanita     : 2,218 (49.2%)

=== Distribusi region ===
  zilinsky kraj, trstena: 4,505 user (100%; sampling memang per satu region)
  Kandidat lain yang dibandingkan (10 teratas menurut rata-rata teman sesama region):
    dipilih                         region  users  edges  avg_friends
          *         zilinsky kraj, trstena   4505  72004        15.98
                    presovsky kraj, lipany   4365  65752        15.06
                   zilinsky kraj, tvrdosin   4131  50190        12.15
                  presovsky kraj, stropkov   3885  44725        11.51
                      zilinsky kraj, bytca   5955  68487        11.50
                      trnavsky kraj, sered   7292  82019        11.25
              kosicky kraj, velke kapusany   3694  40777        11.04
            kosicky kraj, kralovsky chlmec   4584  49906        10.89
             banskobystricky kraj, krupina   5101  54831        10.75
                   kosicky kraj, krompachy   3255  34659        10.65

=== Umur dan kelengkapan profil ===
  Umur terisi/valid (10-90): 3,064 (68.0%) | min 10 | median 20 | maks 69
  completion_percentage      : min 12 | median 55 | maks 98
  Persentase terisi per kolom: public=100%, completion_percentage=100%, gender=100%, region=100%, last_login=100%, registration=100%, age=68%, body_type=54%, eye_color=67%, hair_color=63%, hair_type=57%, completed_level_of_education=54%, favourite_color=63%, relation_to_smoking=62%, relation_to_alcohol=60%, sign_in_zodiac=64%, marital_status=55%, hobbies=61%

=== Hobi (setelah dipecah dan disaring) ===
  2,513 user punya hobi (55.8%); 60 hobi berbeda; 19,512 pasangan user-hobi
  10 hobi terbanyak: sportovanie (1455), priatelia (1408), pocuvanie hudby (1341), pozeranie filmov (1147), spanie (1016), kupalisko (904), diskoteky (895), tancovanie (825), party (821), pc hry (814)
```

Region `zilinsky kraj, trstena` terpilih karena paling rapat di antara 53 kandidat (15,98 teman sesama region per
user, di atas `presovsky kraj, lipany` dengan 15,06). Persentase "terisi per kolom" menunjukkan kenapa profil
Pokec tidak seragam: kolom opsional seperti `body_type` atau `hair_type` hanya terisi ±55%.

### 02_load_sqlite.py (bagian validasi)

```
=== Validasi jumlah baris ===
  users   : 4,505 baris  (CSV: 4,505)  OK
  hobbies : 19,512 baris (hasil pecahan: 19,512)  OK
            2,513 user punya hobi, 60 hobi berbeda

=== Contoh baris tabel users (3 baris pertama, ditampilkan menurun) ===
  user_id                       199                            831                            1804                          
  public                        0                              1                              0                             
  completion_percentage         19                             12                             76                            
  gender                        0                              1                              0                             
  region                        zilinsky kraj, trstena         zilinsky kraj, trstena         zilinsky kraj, trstena        
  last_login                    2012-05-23 11:23:00            2012-05-25 23:20:15            2012-05-03 20:01:00           
  registration                  2007-06-24 00:00:00            2006-09-24 00:00:00            2007-04-23 00:00:00           
  age                           (NULL)                         22                             19                            
  body_type                     (NULL)                         (NULL)                         priemerna                     
  eye_color                     (NULL)                         (NULL)                         modre                         
  hair_color                    (NULL)                         (NULL)                         hnede                         
  hair_type                     (NULL)                         (NULL)                         po plecia                     
  completed_level_of_education  stredoskolske                  (NULL)                         stredoskolske                 
  favourite_color               (NULL)                         (NULL)                         biela, cierna                 
  relation_to_smoking           (NULL)                         (NULL)                         nefajcim, a nikdy ani nebudem 
  relation_to_alcohol           (NULL)                         (NULL)                         abstinent                     
  sign_in_zodiac                (NULL)                         (NULL)                         strelec                       
  marital_status                (NULL)                         (NULL)                         slobodny(a)                   

=== Contoh baris tabel hobbies ===
 user_id           hobby
    1804    domace prace
    1804 pocuvanie hudby
    1804       priatelia
    1804          spanie

  Hobi terpopuler:
             hobby  jumlah_user
       sportovanie         1455
         priatelia         1408
   pocuvanie hudby         1341
  pozeranie filmov         1147
            spanie         1016

=== Integritas dan index ===
  integrity_check  : ok
  foreign_key_check: OK, tidak ada pelanggaran
  cari user per user_id   : SEARCH users USING INTEGER PRIMARY KEY (rowid=?)
  hobi milik satu user    : SEARCH hobbies USING PRIMARY KEY (user_id=?)
  user pemilik satu hobi  : SEARCH hobbies USING COVERING INDEX idx_hobbies_hobby (hobby=?)

Selesai. Database: D:\Softwares\AnacondaProjects\GraphDatabaseSQLHybrid\data\pokec.db (1.7 MB)
Catatan: edges (pertemanan) sengaja TIDAK ada di SQLite - itu tugas Neo4j (script 03).
```

Ketiga lookup memakai index (`SEARCH ... USING ...`, bukan `SCAN`). Nilai `(NULL)` adalah NULL sungguhan di SQLite,
bukan string kosong.

### 03_sync_to_neo4j.py (dengan `--reset`)

```
CSV dibaca: 4,505 user, 72,004 edge, 19,512 pasangan user-hobi
Terhubung ke Neo4j. Batch size: 1000

=== Reset: menghapus node User dan Hobby lama ===
  :User dihapus: 4,505
  :Hobby dihapus: 60

=== Membuat constraint ===
  user_id_unique: siap
  hobby_name_unique: siap

=== Mengisi graph ===
  [User] batch 1/5  (1,000/4,505 baris)  +1000 node, +0 relasi
  [User] batch 2/5  (2,000/4,505 baris)  +1000 node, +0 relasi
  ... (batch User/Hobby/HAS_HOBBY/FRIEND lainnya dipotong di dokumen ini; total 99 batch) ...
  [FRIEND] selesai dalam 2.6 dtk

=== Ringkasan akhir (isi graph sekarang vs isi CSV) ===
  node User        :    4,505   (CSV: 4,505)  OK
  node Hobby       :       60   (CSV: 60)  OK
  relasi FRIEND    :   72,004   (CSV: 72,004)  OK
  relasi HAS_HOBBY :   19,512   (CSV: 19,512)  OK
  total node        : 4,565
  total relasi      : 91,516

Selesai dalam 7.5 dtk.
Coba di Neo4j Browser:  MATCH (u:User)-[f:FRIEND]->(v:User) RETURN u, f, v LIMIT 50
```

## 3. Keluaran keempat fungsi di `04_hybrid_queries.py`

User demo dipilih otomatis: out-degree di persentil ke-75 (cukup banyak teman, tetapi bukan hub ekstrem).
Tanda `-` berarti NULL di SQLite (user tidak mengisinya).

```
User demo: 37947 | out-degree 26, in-degree 44
user_id age gender                 region completed_level_of_education
  37947   - wanita zilinsky kraj, trstena zakladne, aa uuspesne zvla..
```

### a) `rekomendasi_teman(user_id)`

```
=== a) rekomendasi_teman(37947) - teman dari teman yang belum berteman ===
user_id teman_bersama                  lewat_teman age gender                 region completed_level_of_education
 250680             8 22885, 38600, 47634, 73295..  18 wanita zilinsky kraj, trstena                            -
  58930             7 22885, 38600, 173661, 1838..  18 wanita zilinsky kraj, trstena                     zakladne
  82729             6 22885, 38600, 47634, 17366..  18 wanita zilinsky kraj, trstena                     zakladne
 104167             6 73295, 73485, 228124, 2871..   - wanita zilinsky kraj, trstena                     zakladne
  35918             5 16747, 183818, 228124, 271..  20 wanita zilinsky kraj, trstena                stredoskolske
 357050             5 22885, 38600, 173661, 3566..  20   pria zilinsky kraj, trstena                stredoskolske
 117063             4 38600, 183818, 272913, 306..   -   pria zilinsky kraj, trstena                stredoskolske
 121510             4 16747, 73295, 232380, 287195  20   pria zilinsky kraj, trstena      zakladne, stredoskolske
 129423             4 47634, 272913, 292313, 377..  21 wanita zilinsky kraj, trstena      zakladne, stredoskolske
 149160             4 16747, 73485, 272913, 287195   -   pria zilinsky kraj, trstena                            -
```

Neo4j menelusuri dua hop (teman → teman dari teman), membuang yang sudah terhubung langsung dengan user itu
(arah mana pun), lalu menghitung teman bersama. SQLite menambahkan umur, gender, region, dan pendidikan yang
memang tidak disimpan di graph. Kandidat teratas (`250680`) berbagi 8 teman dengan user demo.

### b) `cari_komunitas_hobi(hobby_name)`

Hobi terpopuler (default):

```
=== b) cari_komunitas_hobi('sportovanie') - klaster user sehobi yang saling berteman ===
  1,455 user punya hobi ini; 1,312 di antaranya tergabung dalam 1 klaster (>= 3 anggota yang saling terhubung).

  Ringkasan klaster (maks 5 terbesar):
  klaster anggota umur_rata2 pria wanita pendidikan_terbanyak
        1    1312       19.0  779    533             zakladne

  Anggota klaster 1 yang paling terhubung di dalam klaster (maks 10):
  ukuran_klaster user_id teman_dalam_klaster age gender                 region completed_level_of_education
            1312   32979                  73   - wanita zilinsky kraj, trstena                     zakladne
            1312  119749                  66  23   pria zilinsky kraj, trstena                stredoskolske
            1312   80462                  63   - wanita zilinsky kraj, trstena                stredoskolske
            1312  176281                  62  15   pria zilinsky kraj, trstena                            -
            1312  300871                  59   -   pria zilinsky kraj, trstena                         ziak
            1312  444111                  58  15 wanita zilinsky kraj, trstena                     zakladne
            1312  104167                  56   - wanita zilinsky kraj, trstena                     zakladne
            1312  123624                  56   -   pria zilinsky kraj, trstena         este som na zakladke
            1312  121510                  53  20   pria zilinsky kraj, trstena      zakladne, stredoskolske
            1312   29697                  51  17 wanita zilinsky kraj, trstena                stredoskolske
```

Hobi yang lebih niche (`--hobby chovatelstvo`, memelihara/beternak hewan):

```
=== b) cari_komunitas_hobi('chovatelstvo') - klaster user sehobi yang saling berteman ===
  196 user punya hobi ini; 93 di antaranya tergabung dalam 13 klaster (>= 3 anggota yang saling terhubung).

  Ringkasan klaster (maks 5 terbesar):
  klaster anggota umur_rata2 pria wanita pendidikan_terbanyak
        1      41       17.0   23     18             zakladne
        2      11       13.1    3      8             zakladne
        3       6       17.3    3      3             zakladne
        4       5       20.8    3      2        stredoskolske
        5       4       12.0    2      2             zakladne

  Anggota klaster 1 yang paling terhubung di dalam klaster (maks 10):
  ukuran_klaster user_id teman_dalam_klaster age gender                 region completed_level_of_education
              41   29904                   6   - wanita zilinsky kraj, trstena                     zakladne
              41  192687                   6  18   pria zilinsky kraj, trstena 1az 8 var skoncim aj ten 9..
              41  322056                   6  16   pria zilinsky kraj, trstena                stredoskolske
              41  440485                   5  16   pria zilinsky kraj, trstena                     zakladne
              41  527515                   5   - wanita zilinsky kraj, trstena                     zakladne
              41  358833                   4  17   pria zilinsky kraj, trstena                            -
              41  358860                   4  17   pria zilinsky kraj, trstena                     zakladne
              41  370030                   4  16 wanita zilinsky kraj, trstena                     zakladne
              41  374321                   4   -   pria zilinsky kraj, trstena                     zakladne
              41  205929                   3   - wanita zilinsky kraj, trstena                         ucen

=== c) user_paling_terhubung(10) - degree centrality ===
user_id out_degree in_degree total_degree age gender completed_level_of_education completion_percentage        registration               marital_status
 103095        185       168          353  19   pria              vyuceny sestron                    78 2007-02-17 00:00:00               vdovec (vdova)
  80462        182       156          338   - wanita                stredoskolske                    59 2008-03-19 00:00:00                  slobodny(a)
 104167        121       132          253   - wanita                     zakladne                    76 2006-05-13 00:00:00 slobodny(a) a mam taky poc..
 291794        108       118          226  17 wanita                            -                    12 2006-10-16 00:00:00                            -
 444084        113       113          226  16 wanita                     zakladne                    91 2008-11-01 00:00:00                            -
  32979        124       101          225   - wanita                     zakladne                    84 2007-04-20 00:00:00             nechal ma cous!(
 123624        110       110          220   -   pria         este som na zakladke                    62 2008-01-11 00:00:00                            -
 279450        103       110          213   - wanita                            -                    40 2007-02-27 00:00:00                            -
 119749        117        94          211  23   pria                stredoskolske                    79 2007-03-19 00:00:00                  slobodny(a)
  55690        103       106          209   -   pria  zakladna :) ledwa ledwa :))                    88 2007-01-16 00:00:00    ani sam newim :)) :dd dd:

=== (bonus) rekomendasi_hobi_sama(37947) - hobi sama, belum berteman ===
user_id hobi_sama                         hobi age gender                 region completed_level_of_education
  29697        14 cestovanie, diskoteky, kin..  17 wanita zilinsky kraj, trstena                stredoskolske
  46065        14 cestovanie, diskoteky, kin..  23 wanita zilinsky kraj, trstena                stredoskolske
 119933        14 cestovanie, diskoteky, kin..  24   pria zilinsky kraj, trstena                stredoskolske
 124972        14 cestovanie, diskoteky, kin..  20 wanita zilinsky kraj, trstena             maturitny rocnik
 133842        14 cestovanie, diskoteky, kin..   - wanita zilinsky kraj, trstena                            -
 146132        14 cestovanie, diskoteky, kin..  19 wanita zilinsky kraj, trstena                     zakladne
 162102        14 cestovanie, diskoteky, kin..  22   pria zilinsky kraj, trstena                stredoskolske
 309719        14 cestovanie, diskoteky, kin..  20 wanita zilinsky kraj, trstena                     zakladne
 345041        14 cestovanie, diskoteky, kin..  15 wanita zilinsky kraj, trstena                            -
 356402        14 cestovanie, diskoteky, kin..   -   pria zilinsky kraj, trstena vysokoskolske, mam mnoho t..
```

Untuk hobi populer (`sportovanie`), 1.312 dari 1.455 pemiliknya (90%) terhubung dalam **satu klaster raksasa**:
hampir semua pemilik hobi itu dapat dicapai satu sama lain lewat rantai pertemanan sesama pemilik hobi. Untuk hobi
niche (`chovatelstvo`) gambarannya lain: dari 196 pemilik hanya 93 (47%) yang tergabung, terpecah menjadi 13 klaster
kecil dengan yang terbesar berisi 41 anggota. Klaster dibentuk dengan traversal sederhana (komponen terhubung),
bukan algoritma community detection.

### c) `user_paling_terhubung(limit=10)`

```
=== c) user_paling_terhubung(10) - degree centrality ===
user_id out_degree in_degree total_degree age gender completed_level_of_education completion_percentage        registration               marital_status
 103095        185       168          353  19   pria              vyuceny sestron                    78 2007-02-17 00:00:00               vdovec (vdova)
  80462        182       156          338   - wanita                stredoskolske                    59 2008-03-19 00:00:00                  slobodny(a)
 104167        121       132          253   - wanita                     zakladne                    76 2006-05-13 00:00:00 slobodny(a) a mam taky poc..
 291794        108       118          226  17 wanita                            -                    12 2006-10-16 00:00:00                            -
 444084        113       113          226  16 wanita                     zakladne                    91 2008-11-01 00:00:00                            -
  32979        124       101          225   - wanita                     zakladne                    84 2007-04-20 00:00:00             nechal ma cous!(
 123624        110       110          220   -   pria         este som na zakladke                    62 2008-01-11 00:00:00                            -
 279450        103       110          213   - wanita                            -                    40 2007-02-27 00:00:00                            -
 119749        117        94          211  23   pria                stredoskolske                    79 2007-03-19 00:00:00                  slobodny(a)
  55690        103       106          209   -   pria  zakladna :) ledwa ledwa :))                    88 2007-01-16 00:00:00    ani sam newim :)) :dd dd:
```

Dua hub teratas (`103095` dengan 185 keluar + 168 masuk = 353, dan `80462` dengan 338) jauh di atas sisanya (≤ 253).
Sebagian isian profil jelas asal-asalan (mis. pria berumur 19 yang berstatus `vdovec (vdova)`), ciri data
buatan pengguna yang asli.

### (bonus) `rekomendasi_hobi_sama(user_id)`

```
=== (bonus) rekomendasi_hobi_sama(37947) - hobi sama, belum berteman ===
user_id hobi_sama                         hobi age gender                 region completed_level_of_education
  29697        14 cestovanie, diskoteky, kin..  17 wanita zilinsky kraj, trstena                stredoskolske
  46065        14 cestovanie, diskoteky, kin..  23 wanita zilinsky kraj, trstena                stredoskolske
 119933        14 cestovanie, diskoteky, kin..  24   pria zilinsky kraj, trstena                stredoskolske
 124972        14 cestovanie, diskoteky, kin..  20 wanita zilinsky kraj, trstena             maturitny rocnik
 133842        14 cestovanie, diskoteky, kin..   - wanita zilinsky kraj, trstena                            -
 146132        14 cestovanie, diskoteky, kin..  19 wanita zilinsky kraj, trstena                     zakladne
 162102        14 cestovanie, diskoteky, kin..  22   pria zilinsky kraj, trstena                stredoskolske
 309719        14 cestovanie, diskoteky, kin..  20 wanita zilinsky kraj, trstena                     zakladne
 345041        14 cestovanie, diskoteky, kin..  15 wanita zilinsky kraj, trstena                            -
 356402        14 cestovanie, diskoteky, kin..   -   pria zilinsky kraj, trstena vysokoskolske, mam mnoho t..
```

Sepuluh teratas semuanya berbagi 14 hobi dengan user demo (urutan seri ditentukan `user_id`) dan belum berteman
dengannya. Ini rekomendasi berbasis kesamaan hobi, berbeda dari fungsi a yang berbasis kedekatan di jaringan.

## 4. Perbandingan waktu: SQL JOIN berulang vs Cypher (fungsi d)

```
=== d) bandingkan_performa_query() - teman dari teman dari teman (3 hop) ===
  Tabel friendships dibuat di SQLite: 72,004 baris (0.10 dtk)
  Rencana SQLite: USE TEMP B-TREE FOR count(DISTINCT) | USE TEMP B-TREE FOR sum(DISTINCT) | SEARCH f1 USING PRIMARY KEY (user_id_1=?) | SEARCH f2 USING PRIMARY KEY (user_id_1=?) | SEARCH f3 USING PRIMARY KEY (user_id_1=?)

 user_id  out_degree  jumlah_path  teman_3_level sqlite_join_ms neo4j_ms neo4j_server_ms join_per_neo4j sqlite_distinct_ms
  103095         185       346935           3289         134.75    10.44            9.00         12.91x              12.28
  111493          87       176893           3049          67.77     7.71            7.00          8.79x               9.12
  898460          45        25141           2432          10.44     4.32            3.00          2.42x               3.93
   37947          26        39260           2706          16.00     5.58            4.00          2.87x               5.46
  257768          13         7815           1649           3.28     2.42            1.00          1.36x               1.49

  Median dari 5 pengukuran per user, dalam milidetik. join_per_neo4j > 1 berarti Neo4j lebih cepat.
  jumlah_path = banyaknya path 3-relasi yang disusuri JOIN berulang; teman_3_level = user unik hasilnya.
  neo4j_ms = end-to-end dari Python; neo4j_server_ms = waktu eksekusi di sisi server saja.
  sqlite_distinct_ms = BONUS: SQL yang ditulis ulang (DISTINCT per level), bukan bagian perbandingan utama.

  Hasil SQL JOIN berulang dan Cypher identik untuk semua user uji (jumlah + checksum).
  KESIMPULAN: total 30.5 ms (Neo4j) vs 232.2 ms (SQLite JOIN berulang) -> Neo4j 7.6x lebih cepat pada graph ini.
  BONUS     : SQL yang dioptimalkan total 32.3 ms = 1.06x waktu Neo4j (hasil sama dengan Neo4j untuk 5/5 user).
  Artinya: selisih terutama datang dari SQL JOIN berulang yang menyusuri SEMUA path. Cypher cukup menulis
  [:FRIEND*3] dan tetap cepat; di SQL kita harus tahu trik DISTINCT per level. Selisih pada graph yang jauh
  lebih besar atau hop yang lebih dalam tidak diukur di proyek ini.
```

Cara membaca tabel:
- `jumlah_path` adalah banyaknya path 3-relasi yang harus disusuri JOIN berulang sebelum `DISTINCT`;
  `teman_3_level` adalah user unik yang dihasilkannya. User terbesar menyusuri **346.935 path untuk menghasilkan
  3.289 user unik**.
- Waktu SQLite JOIN berulang nyaris sebanding dengan jumlah path: 0,38-0,42 µs per path pada kelima user
  (134,75 ms / 346.935 path = 0,39 µs; 3,28 ms / 7.815 path = 0,42 µs).
- Neo4j tampaknya membayar biaya tetap ±2 ms (perkiraan kasar dari dua titik data: user terkecil dengan 7.815 path
  pun butuh 2,42 ms), tetapi biaya per path-nya jauh lebih kecil (user terbesar: 10,44 ms untuk 346.935 path,
  ≈0,03 µs per path). Selisih antara `neo4j_ms` (end-to-end dari Python) dan `neo4j_server_ms` sekitar 1-1,5 ms
  (resolusi `neo4j_server_ms` hanya 1 ms), jadi overhead protokol Bolt kecil.
- Hasil kedua database **identik** untuk kelima user (jumlah dan checksum sama).

### Kesimpulan

1. **Untuk pertanyaan seperti yang diminta (SQL JOIN berulang vs Cypher `[:FRIEND*3]`), Neo4j lebih cepat di
   kelima user uji: 1,4× sampai 12,9×, total 7,6× (30,5 ms vs 232,2 ms).** Selisihnya membesar seiring jumlah
   path yang harus disusuri, sesuai dugaan bahwa traversal multi-hop adalah kekuatan graph database. Selama
   pengembangan, selisih total pada banyak kali run berkisar 6×-8× (lihat catatan pemanasan di bawah).
2. **Tetapi bukti ini ada batasnya (dan bagian 5 menjelaskan sebabnya).** SQL yang ditulis ulang dengan `DISTINCT` di tiap level
   (`teman_3_level_dioptimalkan.sql`) menyusul sampai **1,06× waktu Neo4j** (32,3 ms vs 30,5 ms), bahkan lebih
   cepat daripada Neo4j untuk tiga user teringan (≤ 39.260 path). Jadi pada graph sekecil ini yang terbukti adalah:
   (a) Cypher membuat pertanyaan multi-hop sederhana ditulis (`[:FRIEND*3]`) dan langsung cepat, sedangkan di SQL
   cara naifnya menyusuri semua path dan jauh lebih lambat; (b) Neo4j menelusuri path jauh lebih cepat per path.
   Yang **tidak** terbukti: bahwa database relasional tidak mampu. Penjelasan mekanismenya ada di bagian 5: query Cypher di sini
   hanya meminta user unik, sehingga Neo4j memakai `VarLengthExpand(Pruning)`; kalau Cypher juga diminta menghitung path, kerjanya
   sama dengan JOIN berulang dan Neo4j hanya ±1,2× lebih cepat.
3. **Yang tidak diukur di sini:** satu mesin dan satu server; graph kecil (4.505 node, 72.004 edge); hanya lima
   user uji; cache sudah hangat; kedalaman tetap 3 hop; SQLite berjalan di dalam proses Python sedangkan Neo4j
   lewat Bolt. Dua keterbatasan terakhir diuji di bagian 5 (kedalaman 1-4 dan graf sintetis sampai ±544 ribu edge); graf sungguhan
   yang jauh lebih besar tetap tidak diuji.

### Catatan: pemanasan JVM mempengaruhi angka Neo4j

Neo4j berjalan di JVM, jadi server yang baru menyala itu "dingin". Dalam pengamatan terpisah (skrip sementara di luar
proyek, query 3-hop yang sama, server baru menyala):
- Query pertama user terberat makan **±1,2 detik**, lalu 177 → 110 → 67 → 55 ms, dan baru mendekati 11-12 ms setelah
  puluhan pengulangan.
- Total waktu Neo4j untuk kelima user uji: **92 ms** sebelum pemanasan, **32 ms** setelah ±1 detik pemanasan,
  **±29 ms** setelah 4 detik, dan terus membaik pelan sampai **±24 ms** setelah 10 detik atau lebih.

Karena itu benchmark di script 04 memanaskan Neo4j selama 3 detik (`--pemanasan`) sebelum mengukur, dan angka di atas
adalah kinerja *setelah hangat*. Sebelum pemanasan itu ditambahkan, selisih total sempat terukur serendah 5,7× tepat
setelah server dinyalakan. Artinya, pengguna yang baru menekan Start akan merasakan query pertama yang lambat;
hasil benchmark yang dilaporkan tidak menggambarkan hal itu.

## 5. Hasil lengkap notebook 1: menjawab "bisakah graph database dikombinasikan dengan relational database biasa?"

Notebook 1 dijalankan **tiga kali terpisah** (`run1`-`run3`; Neo4j dinyalakan ulang di tiap run sehingga JVM-nya baru) dan angka di
bawah adalah **median antar-run** dari `docs/hasil/gabungan/` (dibuat oleh `scripts/rangkum_run.py`; angka mentah tiap run ada di
`docs/hasil/run1` dst.). Waktu = median beberapa pengulangan bergantian antar mesin setelah pemanasan. Tiap pasangan query hanya
dihitung kalau **hasil kedua mesin identik**. Rasio di atas 1 = Neo4j lebih cepat; di bawah 1 = SQLite lebih cepat.
Seluruh angka hanya berlaku untuk skala ini (4.505 user, 72.004 edge) di satu komputer; kolom "Rentang rasio antar-run" memperlihatkan
seberapa stabil angkanya.

### 5.1 Tes: 40 dari 40 lulus di ketiga run

Konsistensi lintas basis data (himpunan user, edge, dan user-hobi identik; 13.515 nilai atribut duplikat sinkron), sinkronisasi ulang
yang idempoten, deteksi dan perbaikan drift (3 penyimpangan disuntik, 3 terdeteksi persis, 0 tersisa), lima fungsi hybrid sama dengan
jawaban kunci Python murni, 14 pasangan query identik di SQLite dan Neo4j, graf sintetis dihapus dan graf asli utuh, 14 gambar dibuat.

Karakter sampel dibanding seluruh Pokec (SNAP): resiprositas 71,1%, 11,1% user tanpa relasi di sampel,
komponen terbesar 88,3%, koefisien klasterisasi 0,188 (seluruh Pokec: 0,109), diameter efektif
4,0 (seluruh Pokec: 5,2). Sampel lebih rapat karena hanya memuat relasi di dalam satu wilayah.

### 5.2 Pertanyaan yang sama, dua mesin

| Pertanyaan (hasil identik di kedua mesin) | SQLite (ms) | Neo4j (ms) | Lebih cepat | Rentang rasio antar-run |
|---|---|---|---|---|
| Pencarian titik (user_id) | 0,013 | 0,692 | SQLite 52,3× lebih cepat | 0,018–0,019 |
| Agregasi atribut (GROUP BY gender) | 0,983 | 1,8 | SQLite 1,9× lebih cepat | 0,484–0,541 |
| Agregasi struktur (top-10 out-degree) | 4,3 | 18,0 | SQLite 4,2× lebih cepat | 0,236–0,244 |
| Rekomendasi teman (top-10) | 13,6 | 68,7 | SQLite 5,0× lebih cepat | 0,199–0,199 |
| Teman tepat 1 relasi: himpunan unik | 0,353 | 4,8 | SQLite 13,8× lebih cepat | 0,072–0,073 |
| Teman tepat 2 relasi: himpunan unik | 3,6 | 11,2 | SQLite 3,1× lebih cepat | 0,293–0,327 |
| Teman tepat 3 relasi: himpunan unik | 31,2 | 27,4 | Neo4j 1,1× lebih cepat | 1,101–1,208 |
| Teman tepat 4 relasi: himpunan unik | 74,0 | 54,0 | Neo4j 1,4× lebih cepat | 1,347–1,385 |
| Teman tepat 2 relasi: semua path | 5,7 | 11,7 | SQLite 2,1× lebih cepat | 0,454–0,511 |
| Teman tepat 3 relasi: semua path | 230,6 | 194,9 | Neo4j 1,2× lebih cepat | 1,183–1,215 |
| Teman tepat 4 relasi: semua path | 1.135,7 | 911,6 | Neo4j 1,2× lebih cepat | 1,237–1,276 |
| Teman tepat 3 relasi: JOIN vs pruning | 230,6 | 27,4 | Neo4j 8,4× lebih cepat | 8,151–8,752 |
| Jalur terpendek (maks 8 relasi) | 1.156,2 | 31,3 | Neo4j 36,6× lebih cepat | 35,624–37,071 |
| Teman dari teman + filter atribut | 4,6 | 8,6 | SQLite 1,9× lebih cepat | 0,507–0,547 |

Cara membaca: SQLite menang telak pada pencarian satu baris dan pada traversal pendek (1-2 relasi); Neo4j menang pada jalur terpendek
dan pada penelusuran 3-4 relasi yang ditulis "naif" di SQL. Pada penelusuran 3-4 relasi yang setara (sama-sama menyusuri semua path, atau
sama-sama hanya himpunan unik) keunggulan Neo4j hanya ±1,1-1,4×.

### 5.3 Teman tepat k relasi: empat cara

Waktu dalam ms. "Semua path" = SQL JOIN berulang vs Cypher dengan `count(p)`; "himpunan unik" = SQL `DISTINCT` per level vs Cypher tanpa
`count(p)`. Satu kasus (user 111493, k=4, ±7,8 juta path) tidak dijalankan untuk dua cara yang menyusuri semua path.

| User (out-degree) | k | Jumlah path | User unik | SQLite JOIN | Neo4j semua path | SQLite DISTINCT | Neo4j pruning |
|---|---|---|---|---|---|---|---|
| 103095 (185) | 1 | 185 | 185 | 0,10 | 0,96 | 0,07 | 0,97 |
| 111493 (87) | 1 | 87 | 87 | 0,11 | 1,14 | 0,09 | 1,29 |
| 898460 (45) | 1 | 45 | 45 | 0,09 | 0,91 | 0,07 | 0,96 |
| 37947 (26) | 1 | 26 | 26 | 0,07 | 0,83 | 0,05 | 0,77 |
| 257768 (13) | 1 | 13 | 13 | 0,07 | 0,71 | 0,05 | 0,73 |
| 103095 (185) | 2 | 7.375 | 1.530 | 3,06 | 4,46 | 1,82 | 4,18 |
| 111493 (87) | 2 | 3.765 | 1.064 | 1,60 | 3,08 | 1,01 | 2,97 |
| 898460 (45) | 2 | 847 | 446 | 0,39 | 1,50 | 0,30 | 1,50 |
| 37947 (26) | 2 | 938 | 632 | 0,48 | 1,63 | 0,34 | 1,61 |
| 257768 (13) | 2 | 255 | 190 | 0,17 | 1,09 | 0,15 | 1,13 |
| 103095 (185) | 3 | 346.935 | 3.289 | 133,07 | 108,96 | 11,72 | 9,75 |
| 111493 (87) | 3 | 176.893 | 3.049 | 68,03 | 56,71 | 8,84 | 7,11 |
| 898460 (45) | 3 | 25.141 | 2.432 | 10,58 | 9,82 | 3,48 | 3,75 |
| 37947 (26) | 3 | 39.260 | 2.706 | 15,70 | 15,03 | 5,48 | 4,50 |
| 257768 (13) | 3 | 7.815 | 1.649 | 3,25 | 3,77 | 1,61 | 2,16 |
| 111493 (87) | 4 | 7.826.900 | 3.725 | dilewati | dilewati | 24,27 | 17,60 |
| 898460 (45) | 4 | 927.991 | 3.620 | 376,05 | 304,78 | 17,41 | 11,97 |
| 37947 (26) | 4 | 1.594.788 | 3.651 | 642,63 | 509,82 | 19,71 | 15,33 |
| 257768 (13) | 4 | 276.339 | 3.357 | 116,99 | 96,99 | 12,23 | 9,09 |

- Biaya per path (regresi atas data asli + sintetis): **SQLite JOIN 0,42 µs**
  (antar-run: 0,421, 0,422, 0,423), **Neo4j 0,34 µs**
  (antar-run: 0,331, 0,345, 0,338), R² 0,996 dan 0,996. Keduanya linear terhadap jumlah path.
- `EXPLAIN` menunjukkan sebabnya: query dengan `count(p)` memakai `VarLengthExpand(All)` (menyusuri semua path), query tanpa `count(p)` memakai
  `VarLengthExpand(Pruning)` (tiap user dikunjungi sekali per kedalaman, seperti `DISTINCT` per level di SQL).
- Pada k=1 dan k=2 SQLite lebih cepat karena biaya tetap per panggilan ke Neo4j (±0,85 ms, SQLite ±0,006 ms).
  Titik silangnya ada antara k=2 dan k=3.

### 5.4 Jalur terpendek (maks 8 relasi, 20 pasangan; Cypher = SQL recursive CTE = BFS Python)

| Panjang jalur terpendek | Jumlah pasangan | SQLite (ms, median) | Neo4j (ms, median) |
|---|---|---|---|
| 2 relasi | 3 | 5,1 | 1,10 |
| 3 relasi | 8 | 30,6 | 1,53 |
| 4 relasi | 3 | 34,8 | 1,75 |
| 5 relasi | 1 | 81,4 | 1,78 |
| 6 relasi | 1 | 100,5 | 2,06 |
| tidak terhubung | 4 | 156,7 | 1,75 |

Waktu Neo4j hampir datar karena `shortestPath` mencari dari kedua ujung; pencarian melebar di SQL tumbuh dengan jarak, dan paling lama pada
pasangan yang tidak terhubung (seluruh graf harus dijelajahi).

### 5.5 Tiga strategi untuk "teman dari teman yang pria berumur 20-30"

| User (out-degree) | Id dikirim ke SQLite | S1 semua SQLite (ms) | S2 semua Neo4j (ms) | S3 hybrid (ms) |
|---|---|---|---|---|
| 103095 (185) | 1.530 | 2,67 | 3,33 | 34,9 |
| 111493 (87) | 1.064 | 1,13 | 1,91 | 23,9 |
| 898460 (45) | 446 | 0,30 | 1,14 | 9,9 |
| 37947 (26) | 632 | 0,37 | 1,35 | 13,8 |
| 257768 (13) | 190 | 0,12 | 0,87 | 4,6 |

Ketiganya menghasilkan himpunan yang sama. S3 (hybrid) paling lambat karena id harus dikirim dari Neo4j ke Python lalu disaring SQLite, tetapi hanya S3
yang tidak memerlukan atribut diduplikasi di node.

### 5.6 Biaya menggabungkan

- **Lintas batas** (mengambil atribut N user):

| Jumlah user | SQLite (ms) | Neo4j (ms) | Rasio |
|---|---|---|---|
| 10 | 0,77 | 1,5 | 2,0× |
| 100 | 1,07 | 4,7 | 4,3× |
| 1.000 | 2,48 | 31,0 | 12,5× |
| 4.505 | 8,90 | 131,5 | 14,8× |

- **Biaya tetap per panggilan:** SQLite 0,006 ms vs Neo4j 0,85 ms.
- **Query pertama di Neo4j yang baru menyala:** 463, 467, 458 ms (tiga run), lalu turun ke ±17 ms setelah belasan panggilan.
- **Data ganda:** 13.515 nilai atribut di node Neo4j; tabel `friendships` di SQLite (salinan 72.004 edge) sebesar
  0,99 MB dari berkas `pokec.db` 2,70 MB.
- **Ruang disk Neo4j:** ±5,5 MB diukur pada store yang belum pernah memuat graf sintetis (satu kali, saat pengembangan). Setelah uji skala, berkas
  store tidak menyusut (±28,6 MB walau isinya sama); angka run di `docs/hasil/` memuat ukuran yang lebih besar itu.
- **Sinkronisasi:** memuat ulang seluruh graf ke Neo4j (`03_sync_to_neo4j.py`, idempoten) ±3,3 detik;
  memperbaiki 3 atribut yang menyimpang ±35 ms.
- **Memuat data:** graf sintetis 544.025 edge dimuat ke Neo4j dalam 7,8 detik vs SQLite 0,72 detik.
- **Menyalakan Neo4j dari mati:** ±13 detik; SQLite tidak perlu dinyalakan.

### 5.7 Skala: hub, tepat 3 relasi

| Graf | Hub (out-degree) | Jumlah path | SQLite JOIN | Neo4j semua path | SQLite DISTINCT | Neo4j pruning |
|---|---|---|---|---|---|---|
| Sampel Pokec: 4.505 user, 72.004 edge | 185 | 346.935 | 133 | 109 | 11,7 | 9,8 |
| Sintetis: 10.000 user, 135.801 edge | 388 | 474.686 | 199 | 154 | 31,5 | 21,6 |
| Sintetis: 40.000 user, 544.025 edge | 785 | 1.483.449 | 672 | 533 | 114,6 | 89,9 |

Pada graf 7,6× lebih besar, waktu keempat cara naik ±5-10×, dan urutannya sama: dua cara "semua path" jauh di atas dua cara "himpunan unik",
dan Neo4j sedikit di depan SQLite pada tiap pasangan.

### 5.8 Hipotesis

| Hipotesis | Hasil | Bukti |
|---|---|---|
| **H1** Dua basis data konsisten dan hasil gabungan sama persis dengan jawaban kunci | **DIDUKUNG** | 17/17 tes lulus |
| **H2** Pertanyaan yang sama dijawab identik; beda di kinerja dan kemudahan menulis query | **DIDUKUNG** | 14/14 pasangan query identik; median token SQL 46 vs Cypher 17 |
| **H3** Neo4j lebih cepat untuk penelusuran multi-hop, dan selisihnya membesar dengan kedalaman dan jumlah path | **SEBAGIAN** | rasio SQLite/Neo4j (di atas 1 = Neo4j lebih cepat): himpunan unik k=2 0.32×, k=3 1.13×, k=4 1.37×; semua path k=2 0.49×, k=3 1.18×, k=4 1.25×; JOIN vs pruning k=3 8.42×; jalur terpendek 36.58×; hub graf sintetis (SQL/Neo4j): 135,801 edge: semua path 1.29×, unik 1.46×, 544,025 edge: semua path 1.26×, unik 1.27× |
| **H4** SQLite setara atau lebih cepat untuk pencarian titik dan agregasi atribut | **DIDUKUNG** | rasio SQLite/Neo4j: pencarian titik 0.019, agregasi atribut 0.529, agregasi struktur 0.240 (di bawah 1 = SQLite lebih cepat) |
| **H5** Duplikasi atribut menimbulkan risiko ketidaksinkronan yang dapat dideteksi otomatis | **DIDUKUNG** | 3 ketidaksinkronan disuntik, 3 terdeteksi (tepat: True), 0 tersisa setelah perbaikan |

**H3 hanya SEBAGIAN didukung**, dan itu hasil yang jujur: Neo4j lebih cepat mulai k=3 dan pada jalur terpendek, selisihnya membesar dengan kedalaman,
tetapi pada 1-2 relasi SQLite lebih cepat, dan terhadap SQL yang ditulis dengan baik selisihnya hanya ±1,1-1,4×.

### 5.9 Batas

Satu komputer dan satu sampel dari satu wilayah (4.505 user); graf sintetis hanya sampai ±544 ribu edge; beban satu pengguna (tanpa konkurensi); versi
perangkat lunak tertentu (Neo4j 5.26.31 Community, SQLite 3.53.4); SQLite dipanggil di dalam proses sedangkan Neo4j lewat Bolt, sehingga
perbedaan waktu mencampur mesin dan cara pemanggilan (kolom `neo4j_server_ms` di `docs/hasil/` memisahkan waktu di server, resolusi 1 ms).

## 6. Menjalankan ulang

```powershell
python scripts/01_subsample_data.py
python scripts/02_load_sqlite.py
python scripts/03_sync_to_neo4j.py --reset
python scripts/04_hybrid_queries.py
python scripts/04_hybrid_queries.py --hobby chovatelstvo --skip-benchmark
```

Untuk bagian 5: jalankan `notebooks/1_tes_semua.ipynb` (Run All), atau tiga kali dengan `HASIL_SUBDIR=run1`/`run2`/`run3` lalu
`python scripts/rangkum_run.py run1 run2 run3`.

Hasil sampling (01) bersifat deterministik, jadi jumlah data di atas akan sama persis di mesin Anda; hanya angka
waktu di bagian 4 yang berbeda.
