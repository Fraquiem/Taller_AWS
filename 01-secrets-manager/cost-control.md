# Control de costos — punto 1

Región: `us-east-2`.

Servicio: AWS Secrets Manager.

Recursos creados: un secreto temporal de prueba, cifrado con la clave administrada por AWS para Secrets Manager. No se creó Lambda de rotación, KMS customer-managed key, VPC, EC2 ni otro recurso auxiliar.

Configuración seleccionada: un secreto y dos lecturas `GetSecretValue`, una actualización `PutSecretValue` y operaciones de creación/eliminación. El valor fue ficticio y no se guardó en el repositorio.

La página oficial de precios consultada el 2026-09-29 publica USD 0.40 por secreto-mes y USD 0.05 por 10,000 llamadas API: <https://aws.amazon.com/secrets-manager/pricing/>. El costo horario aproximado del almacenamiento de un secreto es `0.40 / (365 × 24) = USD 0.0000457/h`; la prueba realizó pocas llamadas, por debajo de una fracción de centavo. El costo exacto de la cuenta puede verse afectado por créditos o Free Tier.

No hay un componente que cobre por tráfico. Un secreto activo genera almacenamiento aunque no se consulte; las llamadas API se cobran por volumen. Consultar repetidamente el mismo secreto aumenta las llamadas, no crea secretos adicionales. Para una aplicación de alta frecuencia conviene recuperar una vez y conservar el valor en memoria durante la vida segura del proceso, con una estrategia de expiración adecuada; no debe registrarse ni persistirse sin necesidad.

`PutSecretValue` fue una actualización manual que creó una nueva versión y movió `AWSCURRENT`; no es rotación administrada. En esta práctica no se configuró ni ejecutó una Lambda de rotación. La rotación automática debe documentarse y costearse por separado porque puede añadir ejecución de Lambda y permisos adicionales.

La secuencia ejecutable de creación, lectura, actualización y eliminación está en [`README.md`](README.md). Usa variables de entorno y entradas interactivas para no dejar valores sensibles en el código o en archivos.

Limpieza ejecutada: `delete-secret --force-delete-without-recovery` después de las pruebas. La verificación posterior a las 2026-09-29T07:18:45-05:00 devolvió metadatos con `DeletedDate`; el secreto dejó de ser activo. La evidencia reproducible está en `evidence.json`.
