// Properti yang benar-benar tersimpan di tiap label node (dibaca dari database, bukan ditulis tangan).
CALL db.schema.nodeTypeProperties() YIELD nodeLabels, propertyName, propertyTypes
RETURN nodeLabels[0] AS label, propertyName AS properti, propertyTypes[0] AS tipe
ORDER BY label, properti
