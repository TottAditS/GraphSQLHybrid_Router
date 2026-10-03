// Agregasi struktur: 10 user dengan out-degree terbesar.
// Pasangan SQL: agregasi_derajat.sql.
MATCH (u:User)-[:FRIEND]->()
RETURN u.user_id AS user_id, count(*) AS out_degree
ORDER BY out_degree DESC, user_id ASC
LIMIT 10
