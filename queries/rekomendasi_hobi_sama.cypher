// User dengan hobi yang sama dengan $user_id tetapi BELUM berteman (arah mana pun).
// Inilah alasan hobi dimodelkan sebagai node Hobby, bukan sekadar kolom teks.
// Di Neo4j Browser:   :param user_id => 1804    lalu    :param limit => 10
MATCH (me:User {user_id: $user_id})-[:HAS_HOBBY]->(h:Hobby)<-[:HAS_HOBBY]-(other:User)
WHERE other <> me
  AND NOT (me)-[:FRIEND]-(other)
WITH other, h
ORDER BY h.name
RETURN other.user_id AS user_id,
       count(h) AS hobi_sama,
       collect(h.name)[0..5] AS hobi
ORDER BY hobi_sama DESC, user_id ASC
LIMIT $limit
