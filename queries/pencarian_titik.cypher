// Pencarian titik: satu node User lewat user_id (ada constraint UNIQUE, jadi memakai index).
// Pasangan SQL: pencarian_titik.sql. Di Neo4j Browser:   :param user_id => 1804
MATCH (u:User {user_id: $user_id})
RETURN u.user_id AS user_id, u.gender AS gender, u.age AS age, u.region AS region
