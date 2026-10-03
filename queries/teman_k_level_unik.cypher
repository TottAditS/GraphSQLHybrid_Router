// "Teman dari teman ..." tepat __K__ relasi FRIEND, HANYA himpunan user unik di ujung (tanpa menghitung path).
// Karena path tidak diminta, perencana Neo4j boleh memakai VarLengthExpand(Pruning): tiap user dikunjungi sekali per
// kedalaman (seperti DISTINCT per level di SQL), bukan menyusuri semua path. Bandingkan rencananya dengan
// teman_k_level.cypher yang meminta count(p) sehingga SEMUA path harus disusuri:  EXPLAIN <query>
// Di Neo4j Browser:   :param user_id => 1804   (ganti __K__ jadi 3, misalnya)
MATCH (a:User {user_id: $user_id})-[:FRIEND*__K__]->(d:User)
WHERE d <> a
RETURN count(DISTINCT d) AS total,
       sum(DISTINCT d.user_id) AS checksum
