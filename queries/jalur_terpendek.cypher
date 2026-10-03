// Panjang jalur terpendek (mengikuti arah FRIEND, maksimal 8 relasi) dari $a ke $b; tidak ada baris = tidak terhubung.
// Sepadan dengan LDBC SNB Interactive Q13 (single shortest path). Pasangan SQL: jalur_terpendek.sql.
// Di Neo4j Browser:   :param a => 1804    lalu    :param b => 37947
MATCH (a:User {user_id: $a}), (b:User {user_id: $b})
MATCH p = shortestPath((a)-[:FRIEND*..8]->(b))
RETURN length(p) AS panjang
