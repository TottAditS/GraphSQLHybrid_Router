// Inti rekomendasi teman: sama dengan rekomendasi_teman.cypher tetapi tanpa kolom lewat_teman, sehingga pekerjaan
// yang dikerjakan Neo4j sama dengan rekomendasi_teman.sql di SQLite. Dipakai untuk membandingkan waktu (K4/K5 di notebook).
// Di Neo4j Browser:   :param user_id => 1804    lalu    :param limit => 10
MATCH (me:User {user_id: $user_id})-[:FRIEND]->(mutual:User)-[:FRIEND]->(candidate:User)
WHERE candidate <> me
  AND NOT (me)-[:FRIEND]-(candidate)
RETURN candidate.user_id AS user_id,
       count(DISTINCT mutual) AS teman_bersama
ORDER BY teman_bersama DESC, user_id ASC
LIMIT $limit
