// Semua relasi FRIEND (beserta arahnya) di antara sekumpulan user. Dipakai untuk menggambar jaringan di notebook.
// Di Neo4j Browser:   :param ids => [37947, 250680, 58930]
//   lalu, untuk melihat gambarnya langsung:
//   MATCH (a:User)-[r:FRIEND]->(b:User) WHERE a.user_id IN $ids AND b.user_id IN $ids RETURN a, r, b
MATCH (a:User)-[:FRIEND]->(b:User)
WHERE a.user_id IN $ids AND b.user_id IN $ids
RETURN a.user_id AS sumber, b.user_id AS tujuan
