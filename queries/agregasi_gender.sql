-- Agregasi atribut: jumlah user dan umur rata-rata per gender (seluruh tabel dipindai).
-- Pasangan Cypher: agregasi_gender.cypher. AVG mengabaikan NULL (user tanpa umur valid).
SELECT gender,
       COUNT(*)           AS jumlah,
       ROUND(AVG(age), 6) AS umur_rata2
FROM users
GROUP BY gender
ORDER BY gender;
