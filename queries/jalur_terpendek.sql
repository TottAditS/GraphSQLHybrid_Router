-- Panjang jalur terpendek dari :a ke :b (mengikuti arah, maksimal 8 relasi) dengan recursive CTE = pencarian
-- melebar (BFS) di SQL. Pasangan Cypher: jalur_terpendek.cypher. Parameter: :a, :b
-- SQLite memproses antrean CTE secara FIFO, jadi baris dengan kedalaman lebih kecil muncul lebih dulu dan
-- LIMIT 1 menghentikan pencarian begitu :b ditemukan. UNION (bukan UNION ALL) membuang pasangan (node, kedalaman) kembar.
WITH RECURSIVE jangkauan(node, kedalaman) AS (
    SELECT :a, 0
    UNION
    SELECT f.user_id_2, j.kedalaman + 1
    FROM jangkauan AS j
    JOIN friendships AS f ON f.user_id_1 = j.node
    WHERE j.kedalaman < 8
)
SELECT kedalaman AS panjang
FROM jangkauan
WHERE node = :b
LIMIT 1;
