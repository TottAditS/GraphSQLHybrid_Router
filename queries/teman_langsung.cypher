// Teman langsung (relasi FRIEND keluar) dari $user_id. Dipakai untuk menggambar jaringan di notebook.
// Di Neo4j Browser:   :param user_id => 37947
MATCH (:User {user_id: $user_id})-[:FRIEND]->(f:User)
RETURN f.user_id AS user_id
ORDER BY user_id
