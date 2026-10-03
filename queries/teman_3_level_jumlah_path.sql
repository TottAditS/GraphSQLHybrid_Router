-- Berapa banyak path 3-relasi yang harus disusuri oleh teman_3_level.sql (sebelum DISTINCT)?
-- Hanya untuk penjelasan di bandingkan_performa_query(); TIDAK ikut dihitung waktunya.
-- Parameter: :user_id
SELECT COUNT(*) AS jumlah_path
FROM friendships AS f1
JOIN friendships AS f2 ON f2.user_id_1 = f1.user_id_2
JOIN friendships AS f3 ON f3.user_id_1 = f2.user_id_2
WHERE f1.user_id_1 = :user_id
  AND f3.user_id_2 <> :user_id
  AND NOT (f3.user_id_1 = f1.user_id_1 AND f3.user_id_2 = f1.user_id_2);
