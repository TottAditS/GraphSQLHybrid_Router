-- BONUS: pertanyaan yang sama dengan teman_3_level.sql, tetapi SQL-nya ditulis ulang.
-- Alih-alih menyusuri SEMUA path (jumlahnya meledak seiring jumlah teman), tiap level
-- langsung membuang duplikat (DISTINCT) sebelum lanjut ke level berikutnya.
-- Dipakai di bandingkan_performa_query() sebagai pembanding tambahan yang adil: ini
-- menunjukkan seberapa jauh SQL bisa dioptimalkan oleh orang yang tahu triknya.
-- Catatan: query ini menghitung user yang bisa dicapai lewat 3 langkah (boleh melewati
-- relasi yang sama dua kali), jadi pada kasus tepi yang sangat jarang hasilnya bisa
-- berbeda tipis dari Cypher *3. Parameter: :user_id
WITH level1 AS (
    SELECT DISTINCT user_id_2 AS id FROM friendships WHERE user_id_1 = :user_id
), level2 AS (
    SELECT DISTINCT f.user_id_2 AS id FROM friendships AS f JOIN level1 ON f.user_id_1 = level1.id
), level3 AS (
    SELECT DISTINCT f.user_id_2 AS id FROM friendships AS f JOIN level2 ON f.user_id_1 = level2.id
)
SELECT COUNT(*) AS total,
       COALESCE(SUM(id), 0) AS checksum
FROM level3
WHERE id <> :user_id;
