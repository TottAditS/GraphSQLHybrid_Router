-- Pencarian titik: profil satu user lewat user_id (PRIMARY KEY, jadi memakai index).
-- Pasangan Cypher: pencarian_titik.cypher. Parameter: :user_id
-- Hanya kolom yang juga ada di node Neo4j (gender, age, region), supaya hasil keduanya bisa dibandingkan.
SELECT user_id, gender, age, region
FROM users
WHERE user_id = :user_id;
