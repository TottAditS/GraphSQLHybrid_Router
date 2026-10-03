// Agregasi atribut: jumlah user dan umur rata-rata per gender, memakai atribut yang diduplikasi di node User.
// Pasangan SQL: agregasi_gender.sql. avg() mengabaikan null, sama seperti AVG di SQL.
MATCH (u:User)
RETURN u.gender AS gender,
       count(*) AS jumlah,
       round(avg(u.age), 6) AS umur_rata2
ORDER BY gender
