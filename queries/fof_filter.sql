-- Teman dari teman (tepat 2 relasi) yang lolos filter atribut: pria berumur 20-30. Strategi S1 = semuanya di SQL.
-- Pasangan: fof_filter.cypher (S2, atribut di node Neo4j) dan fof_ids.cypher (S3, hybrid). Parameter: :user_id
SELECT COUNT(DISTINCT u.user_id)            AS total,
       COALESCE(SUM(DISTINCT u.user_id), 0) AS checksum
FROM friendships AS f1
JOIN friendships AS f2 ON f2.user_id_1 = f1.user_id_2
JOIN users       AS u  ON u.user_id    = f2.user_id_2
WHERE f1.user_id_1 = :user_id
  AND u.user_id <> :user_id
  AND u.gender = 1
  AND u.age BETWEEN 20 AND 30;
