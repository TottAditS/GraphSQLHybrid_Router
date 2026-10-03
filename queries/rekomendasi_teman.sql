-- Rekomendasi teman versi SQL: "teman dari teman" yang belum terhubung langsung (arah mana pun) dengan :user_id,
-- diurutkan menurut jumlah teman bersama. Pasangan Cypher: rekomendasi_teman.cypher.
-- Parameter: :user_id, :limit
SELECT f2.user_id_2                  AS user_id,
       COUNT(DISTINCT f1.user_id_2)  AS teman_bersama
FROM friendships AS f1
JOIN friendships AS f2 ON f2.user_id_1 = f1.user_id_2
WHERE f1.user_id_1 = :user_id
  AND f2.user_id_2 <> :user_id
  AND NOT EXISTS (
        SELECT 1 FROM friendships AS x
        WHERE (x.user_id_1 = :user_id AND x.user_id_2 = f2.user_id_2)
           OR (x.user_id_1 = f2.user_id_2 AND x.user_id_2 = :user_id))
GROUP BY f2.user_id_2
ORDER BY teman_bersama DESC, user_id ASC
LIMIT :limit;
