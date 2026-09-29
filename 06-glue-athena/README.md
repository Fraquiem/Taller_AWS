# Punto 6 — AWS Glue Data Catalog + Athena

Artefactos locales para el punto 6. El objetivo es distinguir **datos** (objetos CSV
que permanecen en S3) de **metadatos** (base de datos, tabla y esquema en Glue Data
Catalog) y consultarlos con Athena. Todo usa `us-east-2` y los tags
`Project=EIA-AWS-Activity`, `Environment=Lab`, `Point=6`.

- `deploy_cleanup.py` es **dry-run por defecto** y con `--execute` ejecuta el
  ciclo real en `us-east-2`, conservando evidencia sanitizada.
- La ejecución real creó un bucket efímero cifrado y bloqueado públicamente,
  un role Glue efímero, catálogo/crawler y workgroup Athena; después ejecutó
  las consultas y eliminó todos los recursos.
- `evidence/preflight.json`, `infrastructure.json`, `workload.json` y
  `cleanup.json` contienen evidencia observada de esa ejecución. `state.json`
  fue transitorio y se eliminó antes de entregar.
- No se copiaron credenciales, tokens, endpoints privados ni secretos.
- El role Glue se crea a partir de los archivos de trust/policy y se elimina
  en el `finally`; no se requiere un role preexistente.

## Artefactos

- `dataset.csv`: 24 filas de datos más encabezado, con esquema estable y tipos que el
  crawler puede inferir (`order_id`, `customer_id`, `region`, `order_date`, `amount`,
  `status`). Se publica bajo `input/`; la ejecución observada registró la tabla
  descubierta como `input`.
- `glue_workload.py`: validación local del CSV y plan de consultas.
- `queries.sql`: filtro, `GROUP BY`/agregación, verificación de append y ejemplo de
  actualización lógica.
- `deploy_cleanup.py`: wrapper incremental, consultas y cleanup opt-in.
- `iam-operator-policy.json`: permisos del operador, con marcadores de bucket y
  permisos mínimos para crear/pasar/eliminar el role efímero `EIA-P6-Glue-*`.
- `glue-service-role-trust.json` y `glue-service-role-policy.json`: role efímero
  mínimo para el crawler; el wrapper lo crea y lo elimina.
- `evidence/`: evidencia real sanitizada de la última ejecución y `dry-run.json`;
  `state.json` es transitorio y se elimina antes de entregar.

## Qué almacena cada servicio

S3 almacena los bytes del CSV y los resultados de Athena. Glue Data Catalog almacena
la definición lógica: base de datos, tabla, ubicación S3, columnas y tipos; no copia
las filas. El crawler inspecciona objetos bajo `s3://<bucket>/input/`, infiere el
esquema y actualiza la tabla. Athena ejecuta SQL sobre los objetos en S3 usando el
catálogo y escribe resultados en `s3://<bucket>/athena-results/`.

Para corregir un error de inferencia se debe revisar la tabla, normalizar el CSV o
crear/editar la tabla manualmente con tipos explícitos. El crawler es conveniente
para descubrimiento y cambios de esquema; la tabla manual ofrece control exacto,
especialmente en producción. Ninguno convierte CSV en una tabla transaccional.

## Append y update

El wrapper carga el seed, `append.csv` y `update.csv`, vuelve a ejecutar el
crawler y consulta el catálogo. En S3 un append es otro objeto: no se modifica
una fila dentro del CSV. `update.csv` contiene una versión posterior de `order_id`
1003; la consulta usa `max_by(..., order_date)` para seleccionar el importe y
estado vigentes. Para producción, prefiera formato columnar/particionado y un
proceso ACID. Un crawler no mergea ni deduplica registros por sí solo.

## Validación local (no AWS)

```bash
cd 06-glue-athena
python3 -m py_compile glue_workload.py deploy_cleanup.py
python3 glue_workload.py
python3 deploy_cleanup.py
```

La salida debe indicar 24 filas, mostrar el SQL del filtro y de la agrupación, y
contener `DRY-RUN (sin AWS)`. `py_compile` y esta evidencia no demuestran que AWS
haya creado recursos ni que Athena haya devuelto filas reales.

## Ejecución real observada

La ejecución autorizada se realizó con la identidad `user_cli` por defecto y
región fija `us-east-2`:

```bash
python3 deploy_cleanup.py --execute
```

El wrapper creó el role efímero a partir de los JSON locales, esperó la
propagación, ejecutó dos corridas del crawler, cuatro consultas Athena
(filtro, GROUP BY, append y actualización lógica) y eliminó los recursos.

El wrapper genera nombres efímeros, fuerza `us-east-2`, cifra S3 con SSE-S3 y
activa bloqueo de acceso público. Persiste `evidence/state.json` durante la
ejecución para permitir rollback; ese archivo transitorio se elimina antes de
entregar. No guarda credenciales, SecretString ni tokens. Si falla una fase, el
`finally` intenta el cleanup; revisar `cleanup.json` y repetir manualmente
cualquier paso marcado `*_error`.

## IAM mínimo y secretos

El operador necesita únicamente las acciones del archivo de política, restringidas
al bucket/prefijo generado en la revisión final. El role de Glue solo lee el prefijo
S3 y escribe/lee metadatos del catálogo. En una revisión real conviene restringir
ARNs de base de datos/crawler y `iam:PassRole` al ARN exacto del role; nunca usar
`iam:PassRole` con `Resource: "*"`.

Este flujo usa S3, Glue y Athena mediante IAM. No requiere credencial de aplicación
ni secreto en Secrets Manager: no hay base de datos externa, contraseña ni API key.
Si se agrega una conexión JDBC u otro sistema que sí tenga credenciales, deberán
crearse en Secrets Manager y otorgar solo `secretsmanager:GetSecretValue` al role
que las necesite.

## Cleanup y orden

El orden implementado es: detener/eliminar crawler; eliminar la base de datos (y
sus tablas del catálogo); eliminar el workgroup de Athena; borrar objetos y luego
el bucket S3; finalmente eliminar la policy inline y el role Glue efímero. La
evidencia real verificó cero buckets, bases Glue, workgroups y roles con el prefijo
del punto 6. Athena puede dejar resultados en S3 hasta el último paso; por eso el
bucket se borra al final.

## Costes, fuente e hipótesis

Fuentes oficiales (consultar precios regionales antes de una ejecución):

- [AWS Glue pricing](https://aws.amazon.com/glue/pricing/): crawlers se cobran por
  DPU-hora (la tarifa publicada puede cambiar; el crawler usa capacidad mínima y
  duración mínima facturable indicada por AWS).
- [AWS Glue Data Catalog pricing](https://aws.amazon.com/glue/pricing/): revisar
  almacenamiento de objetos/metadatos y solicitudes según volumen; un catálogo de
  laboratorio pequeño suele estar dentro de las asignaciones gratuitas publicadas,
  pero no asumir que es gratis.
- [Amazon Athena pricing](https://aws.amazon.com/athena/pricing/): consultas por TB
  escaneado; aplicar compresión, particiones y columnas seleccionadas. Athena
  aplica el mínimo por consulta que indique la página vigente.
- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/): almacenamiento por GB-mes,
  solicitudes y transferencia; resultados de Athena también son objetos S3.

Como referencia de cálculo publicada en las páginas consultadas (29-09-2026;
confirmar la tarifa efectiva de la región antes de ejecutar):

| Servicio | Referencia publicada | Hipótesis del laboratorio |
|---|---|---|
| Glue crawler | USD 0.44 por DPU-hora; facturación por segundo con mínimo de 10 minutos | 2 DPUs durante 10 min por corrida: `2 × 10/60 × 0.44 = USD 0.1467`; dos corridas: aproximadamente USD 0.2933 |
| Athena | USD 5 por TB escaneado y mínimo de 10 MB por consulta | Dos consultas mínimas: `2 × 10 MB / 1 TB × 5 ≈ USD 0.0001`, antes de redondeos |
| S3 Standard | USD 0.023 por GB-mes para los primeros 50 TB en regiones aplicables | Un CSV pequeño y resultados retenidos brevemente: almacenamiento despreciable, pero solicitudes y transferencia no son cero |
| Glue Data Catalog | consultar la sección de objetos/metadatos de la página de Glue | una base y una tabla pequeñas; no asumir gratuidad fuera de las asignaciones vigentes |

Los importes son una **estimación hipotética**, no un cargo observado ni una
garantía: DPUs/duración efectiva, redondeos, resultados, requests, transferencia,
impuestos y cambios de tarifa pueden alterarlos.

Hipótesis de esta práctica: un bucket efímero en S3 Standard, un crawler que corre
una vez para seed y una vez para append, dos consultas cortas y limpieza inmediata;
el CSV es menor que el mínimo facturable de Athena. Por tanto el crawler y los
mínimos de consulta dominan la cuenta, no los 24 registros. **No se afirma un
importe real**: el importe depende de la tarifa vigente en us-east-2, duración/DPU,
bytes escaneados, solicitudes, retención de resultados y cualquier recurso fuera
de esta carpeta. El volumen examinado incrementa Athena casi linealmente cuando
no hay particiones/column pruning y puede incrementar duración de crawler; el
catálogo y S3 también crecen con objetos, tamaño y retención.

## Evidencia entregada

La ejecución real observada dejó solo evidencia sanitizada: IDs de consultas,
estados, conteos, el resultado seleccionado de `order_id=1003` y orden de cleanup.
No se copiaron respuestas completas de boto3, credenciales, tokens, endpoints
privados ni `SecretString`. `preflight.json`, `infrastructure.json`,
`workload.json` y `cleanup.json` corresponden a la ejecución real; `dry-run.json`
documenta el camino local. `state.json` fue transitorio y se eliminó antes de
entregar.
