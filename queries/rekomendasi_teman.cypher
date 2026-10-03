// Rekomendasi teman: "teman dari teman" yang BELUM terhubung langsung dengan $user_id.
// Dipakai oleh rekomendasi_teman() di scripts/04_hybrid_queries.py.
// Di Neo4j Browser:   :param user_id => 1804    lalu    :param limit => 10
//
// - Traversal mengikuti arah FRIEND: saya -> teman saya -> teman dari teman saya.
// - "Belum terhubung langsung" = tidak ada relasi FRIEND ke arah mana pun antara kandidat dan saya.
// - Peringkat: jumlah teman bersama (makin banyak, makin relevan).
MATCH (me:User {user_id: $user_id})-[:FRIEND]->(mutual:User)-[:FRIEND]->(candidate:User)
WHERE candidate <> me
  AND NOT (me)-[:FRIEND]-(candidate)
WITH candidate, mutual
ORDER BY mutual.user_id
RETURN candidate.user_id AS user_id,
       count(DISTINCT mutual) AS teman_bersama,
       collect(DISTINCT mutual.user_id)[0..5] AS lewat_teman
ORDER BY teman_bersama DESC, user_id ASC
LIMIT $limit
