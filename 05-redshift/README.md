# Punto 5 — Amazon Redshift frente a RDS

Artefactos reproducibles **sin acceso a AWS** para un laboratorio de analítica
relacional. El repositorio no contiene credenciales, secretos, estado Terraform ni
endpoints. El programa es `dry-run` por defecto; ninguna operación AWS ocurre sin
`--execute`.

## Decisión de arquitectura

| Criterio | Redshift Serverless | RDS PostgreSQL/MySQL |
|---|---|---|
| Modelo | Almacén columnar MPP, SQL analítico y COPY desde S3 | Base relacional transaccional en una instancia |
| Escala | Capacidad por RPU y pausado/escala administrada según configuración | Clase de instancia, almacenamiento y réplicas administrados explícitamente |
| Carga de este punto | CSV en S3, filtros, JOIN y agregaciones | Posible, pero requiere extraer/cargar y no es el objetivo de un warehouse |
| Operación | Data API evita gestionar conexiones desde el cliente | Normalmente endpoint/VPC y driver/conexión |
| Elección | **Elegido** para consultas intermitentes cortas | Alternativa si predominan OLTP, transacciones y conexiones persistentes |

Para una práctica breve e intermitente se recomienda **Redshift Serverless** en
`us-east-2`, empezando por el mínimo de capacidad permitido por AWS en el momento
de despliegue. No se debe describir como “gratis” ni como escala-a-cero: existe
consumo mínimo/facturación según capacidad y duración, y S3, Secrets Manager y
transferencia pueden añadir cargos. Confirmar precios regionales antes de crear
recursos. Para una carga continua y predecible debe compararse con un cluster
provisionado; para OLTP de baja latencia, RDS es más apropiado.

## Archivos

- `data/customers.csv`, `data/orders.csv`, `data/order_items.csv`: tres tablas
  relacionadas por `customer_id` y `order_id` (5, 6 y 7 filas).
- `redshift_workload.py`: Boto3 S3 upload, lectura de secreto en runtime,
  CREATE TABLE, COPY, filtro, JOIN, agregación y polling Data API con paginación
  de resultados.
- `redshift-copy-role-trust.json`: confianza para Redshift provisioned y
  Serverless; requisito importante para que COPY pueda asumir el role.
- `redshift-copy-role-policy.json`: mínimo S3 `ListBucket` condicionado al prefijo
  y `GetObject` únicamente sobre los CSV.
- `iam-policy.json`: permisos del operador para upload, `GetSecretValue` y Data API.
- `deploy-cleanup-plan.txt`: procedimiento de despliegue y eliminación, sin
  comandos destructivos automáticos.
- `cost-control.md`: supuestos, límites, limpieza y enlaces oficiales.

## Despliegue efímero y evidencia

`deploy_cleanup.py` es el wrapper opt-in para una corrida real. Genera nombres
únicos, persiste `evidence/state.json` después de cada mutación, escribe
evidencia sanitizada y ejecuta la limpieza en orden (workgroup, namespace, S3,
secreto y role). El secreto se mantiene en memoria/runtime y nunca se guarda en
el estado. La corrida usa `us-east-2` y solicita `baseCapacity=4` RPU; la
creación exitosa del workgroup es la verificación operacional de disponibilidad
de esa capacidad y de las APIs empleadas.

```bash
cd 05-redshift
/ruta/a/venv/bin/python deploy_cleanup.py --execute
```

El wrapper elimina los recursos incluso si la carga falla. Revisar
`evidence/preflight.json`, `infrastructure.json`, `workload.json`,
`cleanup.json` y `state.json`; los archivos no deben contener `SecretString`,
contraseña ni tokens de paginación.

## Validación local (no crea AWS)

Requiere Python 3.10+ y, para importar el programa, `boto3` instalado. El modo
por defecto valida los CSV y construye el plan SQL, pero exige variables de
configuración para evitar destinos ambiguos:

```bash
cd 05-redshift
python3 -m py_compile redshift_workload.py
REDSHIFT_S3_BUCKET=example-lab-bucket \
REDSHIFT_WORKGROUP=example-workgroup \
REDSHIFT_SECRET_ARN=arn:aws:secretsmanager:us-east-2:111122223333:secret:example \
REDSHIFT_COPY_ROLE_ARN=arn:aws:iam::111122223333:role/example-copy \
python3 redshift_workload.py
```

La salida debe indicar conteos de CSV y `DRY-RUN (sin AWS)`. `py_compile` solo
comprueba sintaxis; no es evidencia de ejecución en AWS.

## Ejecución autorizada (opt-in explícito)

Solo después de crear recursos temporales siguiendo el plan, exportar los
valores reales en la shell (no en archivos versionados):

```bash
export AWS_REGION=us-east-2
export REDSHIFT_S3_BUCKET='bucket-temporal-real'
export REDSHIFT_S3_PREFIX='punto5/input'
export REDSHIFT_WORKGROUP='workgroup-temporal'
export REDSHIFT_DATABASE='dev'
export REDSHIFT_SECRET_ARN='arn:aws:secretsmanager:us-east-2:ACCOUNT:secret:NAME'
export REDSHIFT_COPY_ROLE_ARN='arn:aws:iam::ACCOUNT:role/RedshiftPunto5Copy'
python3 redshift_workload.py --execute
```

El secreto debe ser `SecretString` JSON con `username` y `password`. Boto3 lo
lee en runtime, valida su forma y nunca imprime la contraseña. Data API recibe
`SecretArn`; no se pasa la contraseña como argumento SQL ni se registra. No
activar logs wire-level de botocore en este laboratorio.

El programa espera `FINISHED`/falla explícitamente en `FAILED` o `ABORTED`, y usa
`NextToken` para todas las páginas de `GetStatementResult`. Los resultados
impresos son únicamente las tres consultas del laboratorio. Tras una ejecución,
seguir inmediatamente la limpieza en `deploy-cleanup-plan.txt`.

## Seguridad y límites

Reemplazar todos los marcadores `REPLACE_*` de las políticas antes de usarlas.
No conceder `s3:*`, `secretsmanager:*` ni permisos IAM al role de COPY. El role de
COPY debe leer únicamente el bucket/prefijo del laboratorio. Usar tags y un
identificador único; no reutilizar un namespace compartido durante la limpieza.
