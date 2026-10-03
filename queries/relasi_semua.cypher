// Seluruh relasi FRIEND (a -> b), untuk membandingkan himpunan edge Neo4j dengan tabel friendships di SQLite.
MATCH (a:User)-[:FRIEND]->(b:User)
RETURN a.user_id AS user_id_1, b.user_id AS user_id_2
