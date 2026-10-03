// Atribut yang diduplikasi di node User (gender, age, region), untuk membandingkannya dengan tabel users di SQLite.
MATCH (u:User)
RETURN u.user_id AS user_id, u.gender AS gender, u.age AS age, u.region AS region
