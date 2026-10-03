// "Teman dari teman ..." tepat __K__ relasi FRIEND (K diganti angka oleh Python). Dasar benchmark kedalaman.
// Semantik Cypher: dalam satu path satu relasi tidak dipakai dua kali; SQL JOIN meniru aturan itu (lihat eksperimen.py).
// `total` = jumlah user unik di ujung; `checksum` = jumlah user_id unik, untuk memastikan himpunannya sama.
// `jumlah_path` = banyak path yang disusuri (sama dengan baris hasil JOIN di SQL).
// Di Neo4j Browser:   :param user_id => 1804   (ganti __K__ jadi 3, misalnya)
MATCH p = (a:User {user_id: $user_id})-[:FRIEND*__K__]->(d:User)
WHERE d <> a
RETURN count(DISTINCT d) AS total,
       sum(DISTINCT d.user_id) AS checksum,
       count(p) AS jumlah_path
