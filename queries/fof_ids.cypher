// Teman dari teman (tepat 2 relasi), HANYA user_id-nya. Strategi S3 = hybrid: Neo4j memberi daftar id,
// lalu Python meminta SQLite menyaring umur dan gender. Pasangan: fof_filter.sql (S1), fof_filter.cypher (S2).
MATCH (a:User {user_id: $user_id})-[:FRIEND*2]->(d:User)
WHERE d <> a
RETURN DISTINCT d.user_id AS user_id
