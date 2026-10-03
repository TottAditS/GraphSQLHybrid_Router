// Pasangan user yang sama-sama punya hobi $hobby DAN saling berteman (langkah 2).
// Arah FRIEND diabaikan (satu arah saja sudah dianggap terhubung) dan tiap pasangan
// hanya muncul sekali (user_a < user_b). Dari pasangan-pasangan inilah klaster dibentuk.
// Di Neo4j Browser:   :param hobby => 'sportovanie'
MATCH (a:User)-[:HAS_HOBBY]->(h:Hobby {name: $hobby})
MATCH (a)-[:FRIEND]-(b:User)-[:HAS_HOBBY]->(h)
WHERE a.user_id < b.user_id
RETURN DISTINCT a.user_id AS user_a, b.user_id AS user_b
