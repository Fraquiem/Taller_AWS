# Punto 3 — Amazon DocumentDB Serverless

Ejecución real en `us-east-2` con Terraform, bastión EC2 y un túnel SSH local. La
configuración mantiene DocumentDB en subredes privadas; el único acceso externo
es SSH al bastión desde la IP autorizada.

> **Estado de la ejecución:** se verificó la oferta `docdb 5.0.0`,
> `db.serverless`, almacenamiento `standard`, con mínimo `0.5` y máximo `1.0`
> DCU. Terraform creó 16 recursos y el cleanup posterior destruyó 16. No hay
> recursos del punto 3 activos.

## Evidencia de la ejecución

Los resultados reproducibles y sin valores de secretos están en [`evidence/`](evidence/):

| Archivo | Hecho observado |
|---|---|
| [`preflight.json`](evidence/preflight.json) | Región, identidad `user_cli`, CIDR confiable y oferta Serverless disponible. |
| [`cost-before.json`](evidence/cost-before.json) | Precios consultados, fórmula y disponibilidad de la oferta antes de aplicar. |
| [`infrastructure.json`](evidence/infrastructure.json) | Cluster `eia-documentdb`, versión 5.0.0, endpoint, `db.serverless`, DCU y bastión. |
| [`security-groups.json`](evidence/security-groups.json) | SSH `22` desde `201.221.176.28/32`; DocumentDB `27017` solo desde el SG del bastión. |
| [`compass.json`](evidence/compass.json) | Estado inicial: Compass instalado, antes de la validación gráfica posterior. |
| [`compass-validation.json`](evidence/compass-validation.json) | Validación de Compass confirmada por el usuario después de corregir `authSource=admin` y `authMechanism=SCRAM-SHA-1`; registra Compass 1.51.0 y la limitación TLS visible en la captura. |
| [`Conexión_Compass.png`](evidence/Conexión_Compass.png) | Captura de Compass 1.51.0 con la conexión `Taller AWS` visible como conectada, la URI y la advertencia de que la validación del certificado TLS/SSL está deshabilitada. |
| [`cleanup-final.json`](evidence/cleanup-final.json) | Estado final posterior a la destrucción: túnel cerrado y recursos del punto 3 ausentes. |
| [`cleanup-audit.json`](evidence/cleanup-audit.json) | Resultado de `terraform destroy` y auditoría de recursos remanentes. |

### Resultados funcionales

El workload Python se conectó por `127.0.0.1:27018` mediante SSH, con TLS y el
CA global de AWS; recuperó las credenciales en tiempo de ejecución desde Secrets
Manager y no imprimió el secreto. El resultado observado fue:

- 10 documentos insertados.
- 4 documentos en el filtro `active=true` y `score >= 70`, ordenados con scores
  `[90, 84, 78, 72]`.
- Agregación para `program=data`: `count=10`, `average_score=76.5`.

MongoDB Compass 1.51.0 fue validado por el usuario después de corregir la
conexión con `authSource=admin` y `authMechanism=SCRAM-SHA-1`. La
[captura de Compass](evidence/Conexión_Compass.png) muestra la conexión
`Taller AWS` en estado conectado, esos parámetros visibles en la URI y la
advertencia de Compass de que la validación del certificado TLS/SSL está
deshabilitada. Por tanto, la conexión GUI tuvo éxito, pero esta evidencia no
prueba validación de la CA en Compass. La validación de la CA sí está observada
en el workload Python, que usó el bundle global de AWS; son resultados
independientes. La captura no expone credenciales ni permite afirmar resultados
de consultas o datos que no sean visibles en ella.

## Costos y comparación
La consulta de precios de `us-east-2` quedó registrada en
[`cost-before.json`](evidence/cost-before.json). La tarifa observada para
DocumentDB Serverless Standard fue **USD 0.0822/DCU-h**:

- Mínimo configurado: `0.5 × 0.0822 = USD 0.0411/h`.
- Máximo configurado: `1.0 × 0.0822 = USD 0.0822/h`.
- Bastión: EC2 `t3.micro`, referencia **USD 0.0104/h**, más EBS gp3 de 8 GiB.
- Secrets Manager: referencia **USD 0.40/mes**.
- Referencia registrada para 4 horas de cómputo mínimo DocumentDB + bastión:
  **USD 0.206**.

La fórmula anterior excluye almacenamiento, I/O, backups, transferencia, IP
pública y cargos de API. No es una factura final; las tarifas pueden cambiar y
deben consultarse nuevamente antes de repetir la práctica.

Se escogió Serverless para una prueba corta porque permite mantener la capacidad
entre 0.5 y 1.0 DCU. Como comparación, el precio consultado para una instancia
aprovisionada `db.t3.medium` fue USD 0.078/instance-h: para 4 horas serían USD
0.312 solo de cómputo de DocumentDB, frente a USD 0.1644 de Serverless al mínimo.
Ambas alternativas requerirían considerar por separado bastión, EBS,
almacenamiento, I/O, backups, transferencia y Secrets Manager.

Fuentes: [precios de Amazon DocumentDB](https://aws.amazon.com/documentdb/pricing/),
[precios EC2 On-Demand](https://aws.amazon.com/ec2/pricing/on-demand/) y
[precios de Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/).

## Arquitectura y seguridad

```text
Computador local
  │ SSH TCP/22 (201.221.176.28/32)
  ▼
Bastión EC2 t3.micro (subred pública)
  │ túnel local: 127.0.0.1:27018 → TCP/27017
  ▼
DocumentDB Serverless (subred privada, TLS)
  SG DocumentDB: TCP/27017 únicamente desde SG del bastión
```

- VPC `10.63.0.0/16`, dos subredes privadas en AZ distintas y una subred
  pública para el bastión.
- El SG del bastión acepta TCP/22 solo desde `201.221.176.28/32`.
- El SG de DocumentDB acepta TCP/27017 únicamente desde el SG del bastión; no
  existe ingreso público `0.0.0.0/0`.
- El bastión requiere IMDSv2 y EBS cifrado. No se creó NAT Gateway.
- El bastión solo reenvía TCP: no necesita leer el secreto ni funciona como
  proxy general.

## DocumentDB frente a MongoDB

DocumentDB implementa un subconjunto de la API y del wire protocol de MongoDB,
no el servidor MongoDB completo. Antes de migrar hay que probar las consultas
reales, operadores, comandos administrativos, índices, transacciones,
change streams, compresión y agregaciones con la versión objetivo.

DocumentDB usa un cluster administrado con almacenamiento distribuido y réplicas
administradas; no se gestionan los mismos procesos, configuración de replica set
ni opciones de almacenamiento que en MongoDB Community o Atlas. En esta práctica
el workload Python validó TLS con el CA de AWS; `retryWrites=false` y
`replicaSet=rs0`. La conexión GUI de Compass tuvo una limitación distinta:
la captura muestra que la validación del certificado TLS/SSL estaba
deshabilitada.

Fuentes: [compatibilidad de DocumentDB](https://docs.aws.amazon.com/documentdb/latest/developerguide/compatibility.html)
y [diferencias funcionales](https://docs.aws.amazon.com/documentdb/latest/developerguide/functional-differences.html).

## Pasos reproducibles

### 1. Preparar variables y crear la infraestructura

Requisitos: Terraform >= 1.5, AWS CLI con permisos para VPC/EC2/DocumentDB
(namespace `rds`) y Secrets Manager, y Python con `boto3` y `pymongo`.
Usar una cuenta o rol temporal; nunca credenciales estáticas en el bastión.

```bash
cd 03-documentdb
export AWS_REGION=us-east-2
export TF_VAR_trusted_cidr="TU.IP.PUBLICA/32"
eval "$(./keypair.sh create)"       # clave privada temporal en /tmp
export KEY_NAME="$TF_VAR_key_name"
read -rsp 'Password DocumentDB: ' TF_VAR_docdb_password
export TF_VAR_docdb_password; echo
./deploy.sh                           # init, validate y plan
terraform apply point3.tfplan         # solo después de revisar el plan
```

`deploy.sh` exige `TF_VAR_docdb_password`, `TF_VAR_trusted_cidr` y
`TF_VAR_key_name`; la contraseña no debe estar en `terraform.tfvars`, historial,
logs, capturas ni este README. Tras aplicar, guardar solo IDs, endpoint y
resultados sin secretos:

```bash
terraform output -raw bastion_public_ip
terraform output -raw docdb_endpoint
terraform output -raw secret_arn
```

### 2. Abrir el túnel y ejecutar Python

Esperar a que la instancia esté `available` y descargar el CA oficial fuera del
repositorio, por ejemplo en `/tmp/global-bundle.pem`:

```bash
curl -o /tmp/global-bundle.pem \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
ssh -i "${DOCDB_KEY_FILE:-/tmp/${KEY_NAME}.pem}" -N \
  -o ExitOnForwardFailure=yes \
  -L 27018:CLUSTER_ENDPOINT:27017 ec2-user@BASTION_PUBLIC_IP
```

En otra terminal, con el túnel activo:

```bash
python -m venv .venv
.venv/bin/pip install boto3 pymongo
export DOCDB_SECRET_ID='ARN_O_NOMBRE_DEL_SECRETO'
export DOCDB_ENDPOINT=127.0.0.1
export DOCDB_PORT=27018
.venv/bin/python documentdb_workload.py \
  --ca-file /tmp/global-bundle.pem \
  --tls-allow-invalid-hostname
```

El script obtiene `username/password` con `secretsmanager:GetSecretValue` en
runtime, inserta los 10 documentos y muestra el resultado JSON sin contraseña.

`--tls-allow-invalid-hostname` agrega `tlsAllowInvalidHostnames=true` **solo**
para esta conexión local: el certificado de DocumentDB identifica el endpoint
real del cluster, mientras que el cliente ve `127.0.0.1` por el túnel y por eso
el nombre no coincide. El CA sigue validándose; no se desactiva TLS. Esta opción
no debe usarse conectándose al endpoint directamente ni como solución para
ignorar la identidad de un host remoto.

La misma opción añade `directConnection=true` **solo al endpoint localhost del
túnel**, evitando que el driver intente descubrir/reconectar direcciones privadas
inaccesibles desde el computador local. No debe usarse para una conexión directa
al cluster ni copiarse a un despliegue donde el cliente pueda alcanzar la
topología de DocumentDB.

### 3. Conexión manual en Compass (validada)

Estos pasos describen la conexión validada por el usuario. Mantener activo el
túnel SSH en `127.0.0.1:27018` y usar una URI con usuario y contraseña
obtenidos de Secrets Manager, sin guardarlos en el README ni en capturas:

```text
mongodb://USUARIO:CONTRASEÑA@127.0.0.1:27018/?authSource=admin&authMechanism=SCRAM-SHA-1&tls=true&tlsCAFile=/tmp/global-bundle.pem&tlsAllowInvalidHostnames=true&replicaSet=rs0&retryWrites=false&directConnection=true
```

La corrección que permitió la conexión fue añadir `authSource=admin` y
`authMechanism=SCRAM-SHA-1`. Aunque la URI incluye `tlsCAFile` y
`tlsAllowInvalidHostnames=true`, la [captura de Compass](evidence/Conexión_Compass.png)
advierte explícitamente que la validación del certificado TLS/SSL está
deshabilitada. Por ello, la conexión GUI sí tuvo éxito, pero no se puede afirmar
que Compass haya validado la CA. La validación de la CA corresponde al workload
Python y no debe atribuirse a Compass.

En un entorno seguro, seleccionar en Compass el archivo de CA confiable
(`/tmp/global-bundle.pem` en esta práctica) y mantener activa la validación del
certificado. Si la versión de Compass admite relajar **solo** la validación del
hostname para el túnel local, esa opción puede usarse con el CA todavía validado;
si no la admite, no se debe deshabilitar la validación del certificado: hay que
usar un nombre que coincida con el certificado o una alternativa de túnel/DNS
compatible. La captura documenta la limitación de esta ejecución y el estado final
se confirma en [`cleanup-final.json`](evidence/cleanup-final.json).

## Secretos y state de Terraform

Terraform crea el secreto desde `TF_VAR_docdb_password`; el bastión no lo lee.
Aunque el valor sea `sensitive`, Terraform puede conservarlo en
`terraform.tfstate`. Por eso:

- No versionar `terraform.tfstate`, `terraform.tfstate.backup`, `point3.tfplan`,
  `.tfvars`, claves privadas ni salidas con credenciales.
- En una ejecución compartida usar backend remoto cifrado y restringir el acceso
  al state; no copiarlo a `evidence/`.
- Las evidencias incluidas aquí contienen `"secret_values": "not recorded"`.

## Limpieza y auditoría

Con la misma configuración y variables de la ejecución:

```bash
export KEY_NAME="$TF_VAR_key_name"
export DOCDB_KEY_FILE="${DOCDB_KEY_FILE:-/tmp/${KEY_NAME}.pem}"
./cleanup.sh
```

Si Terraform no está en `PATH`, invocarlo con la ruta disponible en el entorno
(en la ejecución registrada se usó `../.tools/terraform`), porque `cleanup.sh`
llama al comando `terraform` sin parametrizarlo:

```bash
PATH="../.tools:$PATH" ./cleanup.sh
```

`cleanup.sh` ejecuta `terraform destroy -auto-approve`, elimina el key pair EC2
si `KEY_NAME` está definido y borra la clave privada local. Si un secreto quedó
retenido y se tiene el ARN confirmado, `FORCE_DELETE_SECRET=1` permite eliminarlo
sin ventana de recuperación:

```bash
export SECRET_ARN='ARN_REDACTADO'
export FORCE_DELETE_SECRET=1
./cleanup.sh
```

Después de confirmar el destroy y de no necesitar una auditoría del state,
eliminar los artefactos locales que pueden contener valores sensibles:

```bash
rm -f terraform.tfstate terraform.tfstate.backup point3.tfplan
rm -f "${DOCDB_KEY_FILE:-/tmp/${KEY_NAME}.pem}"
```

No borrar el state antes de completar el destroy si todavía se necesita para que
Terraform rastree los recursos. Verificar además snapshots finales, EBS, EIP,
NAT Gateway y secretos retenidos; no crear evidencias con credenciales.

La auditoría final está en [`cleanup-final.json`](evidence/cleanup-final.json):
`terraform_destroy` registró **16_destroyed**, el túnel quedó cerrado y no se
encontraron DocumentDB, VPC, EC2 en ejecución, EBS, ENI, NAT Gateway, EIP,
keypair ni secreto del punto 3. La evidencia no registra valores de secretos.
