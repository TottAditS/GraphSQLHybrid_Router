// Teman dari teman (tepat 2 relasi) yang lolos filter atribut: pria berumur 20-30. Strategi S2 = semuanya di Neo4j,
// memakai atribut gender dan age yang diduplikasi di node User. Pasangan: fof_filter.sql (S1), fof_ids.cypher (S3).
MATCH (a:User {user_id: $user_id})-[:FRIEND*2]->(d:User)
WHERE d <> a AND d.gender = 1 AND d.age >= 20 AND d.age <= 30
RETURN count(DISTINCT d) AS total, sum(DISTINCT d.user_id) AS checksum
