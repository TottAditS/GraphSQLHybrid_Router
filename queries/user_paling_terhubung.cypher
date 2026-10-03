// Degree centrality sederhana = jumlah relasi FRIEND per user.
//   out_degree : berapa orang yang user ini tandai sebagai teman
//   in_degree  : berapa orang yang menandai user ini sebagai teman
// Pertemanan timbal-balik (A->B dan B->A) dihitung sebagai dua relasi.
// Di Neo4j Browser:   :param limit => 10
MATCH (u:User)
WITH u,
     COUNT { (u)-[:FRIEND]->() } AS out_degree,
     COUNT { (u)<-[:FRIEND]-() } AS in_degree
RETURN u.user_id AS user_id,
       out_degree,
       in_degree,
       out_degree + in_degree AS total_degree
ORDER BY total_degree DESC, user_id ASC
LIMIT $limit
