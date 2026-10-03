// "Teman dari teman dari teman": user yang bisa dicapai lewat TEPAT 3 relasi FRIEND.
// Versi Neo4j untuk benchmark di bandingkan_performa_query() (lawannya: teman_3_level.sql).
// Di Neo4j Browser:   :param user_id => 1804
//
// Aturan Cypher: dalam satu path, satu relasi tidak boleh dipakai dua kali. Query SQL
// meniru aturan itu supaya kedua hasil sama persis. `checksum` (jumlah user_id unik)
// dipakai untuk memastikan kedua sisi mengembalikan himpunan user yang sama.
MATCH (a:User {user_id: $user_id})-[:FRIEND*3]->(d:User)
WHERE d <> a
RETURN count(DISTINCT d) AS total,
       sum(DISTINCT d.user_id) AS checksum
