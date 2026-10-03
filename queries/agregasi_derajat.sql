-- Agregasi struktur: 10 user dengan out-degree terbesar (jumlah teman yang mereka tandai).
-- Pasangan Cypher: agregasi_derajat.cypher. Memakai tabel friendships (salinan untuk benchmark).
SELECT user_id_1 AS user_id,
       COUNT(*)  AS out_degree
FROM friendships
GROUP BY user_id_1
ORDER BY out_degree DESC, user_id ASC
LIMIT 10;
