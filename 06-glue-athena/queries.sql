-- Reemplace glue_catalog, eia_p6_<suffix> y orders por los nombres de la ejecución.
-- Athena engine v3; no contiene resultados inventados.

-- 1) Filtrado: pedidos pagados por encima de 100.
SELECT order_id, customer_id, region, amount, order_date
FROM glue_catalog.eia_p6_<suffix>.orders
WHERE status = 'paid' AND amount > 100
ORDER BY amount DESC;

-- 2) GROUP BY/agregación: total y cantidad por región.
SELECT region, COUNT(*) AS order_count, SUM(amount) AS total_amount,
       AVG(amount) AS average_amount
FROM glue_catalog.eia_p6_<suffix>.orders
GROUP BY region
ORDER BY total_amount DESC;

-- 3) Verificación de append después de subir append.csv y volver a ejecutar crawler.
SELECT COUNT(*) AS row_count_after_append
FROM glue_catalog.eia_p6_<suffix>.orders;

-- 4) Actualización lógica. update.csv publica una versión posterior de 1003.
--    max_by selecciona los valores asociados a la fecha más reciente.
SELECT order_id,
       max_by(amount, order_date) AS latest_amount,
       max_by(status, order_date) AS latest_status,
       max(order_date) AS latest_date
FROM glue_catalog.eia_p6_<suffix>.orders
WHERE order_id = 1003
GROUP BY order_id;
