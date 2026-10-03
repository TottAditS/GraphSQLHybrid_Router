// Jumlah node per label dan jumlah relasi per tipe (untuk gambar model graf).
MATCH (u:User) RETURN 'node' AS jenis, 'User' AS nama, count(u) AS jumlah
UNION ALL
MATCH (h:Hobby) RETURN 'node' AS jenis, 'Hobby' AS nama, count(h) AS jumlah
UNION ALL
MATCH (:User)-[r:FRIEND]->(:User) RETURN 'relasi' AS jenis, 'FRIEND' AS nama, count(r) AS jumlah
UNION ALL
MATCH (:User)-[r:HAS_HOBBY]->(:Hobby) RETURN 'relasi' AS jenis, 'HAS_HOBBY' AS nama, count(r) AS jumlah
