// Seluruh pasangan user-hobi (HAS_HOBBY), untuk membandingkannya dengan tabel hobbies di SQLite.
MATCH (u:User)-[:HAS_HOBBY]->(h:Hobby)
RETURN u.user_id AS user_id, h.name AS hobby
