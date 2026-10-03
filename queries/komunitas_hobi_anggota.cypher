// Semua user yang punya hobi $hobby (langkah 1 pencarian komunitas hobi).
// Di Neo4j Browser:   :param hobby => 'sportovanie'
MATCH (u:User)-[:HAS_HOBBY]->(:Hobby {name: $hobby})
RETURN u.user_id AS user_id
