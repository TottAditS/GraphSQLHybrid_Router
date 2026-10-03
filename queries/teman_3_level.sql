-- "Teman dari teman dari teman" lewat self-JOIN berulang pada tabel friendships (SQLite).
-- Versi SQL untuk benchmark di bandingkan_performa_query() (lawannya: teman_3_level.cypher).
-- Parameter: :user_id
--
-- Satu JOIN per level. Baris terakhir meniru aturan Cypher "satu relasi tidak boleh
-- dipakai dua kali dalam satu path" (satu-satunya pengulangan yang mungkin terjadi
-- adalah A->B, B->A, A->B), sehingga hasil kedua database identik.
-- friendships punya PRIMARY KEY (user_id_1, user_id_2), jadi setiap JOIN memakai index.
SELECT COUNT(DISTINCT f3.user_id_2)            AS total,
       COALESCE(SUM(DISTINCT f3.user_id_2), 0) AS checksum
FROM friendships AS f1
JOIN friendships AS f2 ON f2.user_id_1 = f1.user_id_2
JOIN friendships AS f3 ON f3.user_id_1 = f2.user_id_2
WHERE f1.user_id_1 = :user_id
  AND f3.user_id_2 <> :user_id
  AND NOT (f3.user_id_1 = f1.user_id_1 AND f3.user_id_2 = f1.user_id_2);
