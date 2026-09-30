# Punto 2 — Terraform, Boto3 y AWS CLI (ejecutado)

Las tres variantes se ejecutaron secuencialmente en `us-east-2` con la identidad
`arn:aws:iam::241732001318:user/user_cli`:

1. Terraform: creación, verificación y destrucción.
2. Boto3: creación, verificación y destrucción.
3. AWS CLI: creación, verificación y destrucción.

Cada variante creó S3, una VPC con subredes, EC2 y RDS PostgreSQL; después se
limpiaron sus recursos antes de iniciar la siguiente. Las evidencias JSON están
en [`evidence/`](evidence/). No se modificó IAM durante las ejecuciones.

## Resultado observado y evidencias

| Variante | Creación/verificación | Destrucción/verificación | Resultado observado |
|---|---|---|---|
| Terraform | [`terraform-pre.json`](evidence/terraform-pre.json), [`terraform-verify.json`](evidence/terraform-verify.json) | [`terraform-destroy-verify.json`](evidence/terraform-destroy-verify.json) | S3 OK; EC2 `running`; RDS `available`; VPC `10.42.0.0/16`; el secreto administrado por RDS existió sin leer su valor. |
| Boto3 | [`boto3-pre.json`](evidence/boto3-pre.json), [`boto3-verify.json`](evidence/boto3-verify.json) | [`boto3-destroy-verify.json`](evidence/boto3-destroy-verify.json) | S3 OK; EC2 `running`; RDS `available`; almacenamiento cifrado; RDS privado y Single-AZ. |
| AWS CLI | [`cli-pre.json`](evidence/cli-pre.json), [`cli-create-verify.json`](evidence/cli-create-verify.json) | [`cli-destroy-verify.json`](evidence/cli-destroy-verify.json), [`cli-tag-audit.json`](evidence/cli-tag-audit.json) | Bucket `eia-aws-activity-eia-lab-1790698311`, EC2 `i-0740d32db10d8924c`, RDS `eia-lab-eia-lab-1790698311`, VPC `vpc-003f2edfdac13db82`; en la verificación EC2 estaba `running`, RDS `creating` y S3 respondió OK. |

La auditoría final de la variante CLI devolvió listas vacías para EC2 activo, VPC,
S3, RDS, volúmenes disponibles/en uso, NAT, interfaces de red y direcciones
Elastic. `describe-instances` por el ID de EC2 devolvió código 0 porque AWS
conserva el registro histórico de una instancia terminada; no representa un
recurso activo ni facturable. El waiter de eliminación de RDS terminó antes de
la auditoría.

En el primer intento de la variante CLI se usó un parámetro inválido y la
secuencia quedó parcial. Se limpiaron los recursos de ese intento, se corrigió
el script y se ejecutó una única variante CLI completa, cuyos IDs y resultados
son los enlazados arriba. Este detalle permite reproducir la diferencia entre
un intento parcial y la ejecución válida sin presentar el primer intento como
una cuarta variante.

## Diseño y seguridad observados

- S3 privado con bloqueo de acceso público, cifrado SSE-S3 y expiración de objetos
  a siete días.
- EC2 `t3.micro` en una subred pública, IMDSv2 obligatorio y EBS gp3 cifrado de
  8 GiB. La regla SSH usa `trusted_cidr`; para una prueba real debe ser la IP
  pública del operador en `/32`, no `0.0.0.0/0`.
- RDS PostgreSQL `db.t3.micro`, Single-AZ, 20 GiB gp3 cifrados, privado y en
  dos subredes privadas. Solo acepta TCP 5432 desde el security group de EC2.
- No se creó NAT Gateway, Elastic IP, endpoint, Multi-AZ ni snapshot final.
- `manage_master_user_password` hace que RDS administre la contraseña en
  Secrets Manager. Ninguna evidencia contiene el valor del secreto; solo se
  verificó su existencia/metadatos.
- La AMI de EC2 se obtuvo del parámetro público de Amazon Linux 2023. El
  dataset `dataset.csv` es mínimo y no contiene secretos.

## Autenticación, IAM y estado

Las operaciones normales se realizaron con `user_cli`. Terraform, Boto3 y AWS
CLI usan la cadena estándar de credenciales (perfil, variables de entorno,
configuración o credenciales temporales). Compruebe la identidad antes de
crear recursos:

```bash
aws sts get-caller-identity --query Arn --output text
aws configure get region
```

El resultado esperado es el ARN de `user_cli` y la región `us-east-2`. Root no
es necesario para crear ni destruir estos recursos: se reserva únicamente para
la auditoría de Billing/Cost Explorer cuando la cuenta lo requiera. `iam-policy.json`
es una referencia del mínimo operativo; no se adjunta ni modifica mediante
esta práctica. Sus permisos de creación usan `Resource: *` donde el ARN aún no
existe y deben restringirse según la política de laboratorio de la cuenta.

El estado de Terraform contiene IDs, atributos de red y referencias al secreto
administrado por RDS. No se debe publicar. `.tfstate`, `.tfvars` y el plan están
ignorados por este directorio; las evidencias enlazadas son la salida sanitizada
de verificación, no el estado completo.

## Terraform (primero)

Desde la raíz del repositorio, el ejecutable disponible es `.tools/terraform`:

```bash
cd 02-terraform-sdk-cli
../.tools/terraform init
../.tools/terraform fmt -check
../.tools/terraform validate
../.tools/terraform plan -out terraform.tfplan
# Solo después de revisar el plan:
../.tools/terraform apply terraform.tfplan
../.tools/terraform output
# Al terminar la prueba:
../.tools/terraform destroy
../.tools/terraform plan -destroy
```

Si existe un perfil explícito, puede añadirse
`-var='aws_profile=user_cli'`; de lo contrario, la cadena estándar debe
resolver a `user_cli`. No aplique un plan que apunte a otra región o identidad.
La ejecución documentada y su limpieza están en los archivos Terraform de la
tabla de evidencias.

## Boto3 (segundo)

Requiere Python, `boto3` y credenciales ya configuradas. La preparación del
entorno no crea usuarios ni credenciales:

```bash
cd 02-terraform-sdk-cli
python -m venv .venv
. .venv/bin/activate
python -m pip install boto3
python deploy_boto3.py create --region us-east-2 --trusted-cidr 127.0.0.1/32
python deploy_boto3.py verify --region us-east-2
python deploy_boto3.py destroy --region us-east-2
```

`boto3-state.json` contiene solo IDs y se ignora. Si el proceso se interrumpe,
consérvelo hasta completar la limpieza y no lo edite con contraseñas. El script
reutiliza clientes, espera la eliminación de RDS/EC2 y elimina los objetos S3
antes del bucket.

## AWS CLI (tercero)

Revise el script antes de ejecutarlo y no lo inicie hasta haber verificado la
destrucción de Boto3. `aws-cli-sequence.sh` captura IDs, crea la red mínima,
configura S3, lanza EC2 con IMDSv2, crea RDS con contraseña administrada,
verifica y limpia en orden inverso. Antes de `run-instances`, cambie
`TRUSTED_CIDR` por un `/32` real si se necesita SSH. El bloque final espera RDS
y EC2, elimina un S3 no vacío, elimina el subnet group y desmonta VPC/IGW.

```bash
cd 02-terraform-sdk-cli
AWS_PROFILE=user_cli AWS_REGION=us-east-2 bash aws-cli-sequence.sh
```

La ejecución completa documentada es la de `cli-create-verify.json`; no se debe
interpretar el comentario histórico del script como ausencia de ejecución.

## Costos observados y estimación

La estimación previa para `us-east-2`, antes de impuestos, créditos y Free Tier,
fue de aproximadamente **USD 0.033 por hora** o **USD 5.54 por 168 horas por
variante**. Incluye EC2 `t3.micro`, RDS `db.t3.micro`, 8 GiB de EBS, 20 GiB de
RDS y un secreto prorrateado; S3 del dataset queda por debajo de un centavo,
sujeto a requests. Es una estimación, no una factura; los precios de referencia
están en [`cost-control.md`](cost-control.md).

EC2 y RDS cobran mientras están activos aunque no reciban tráfico. EBS, S3 y
Secrets Manager pueden seguir generando cargos mientras existan datos o
secretos. Snapshots/backups retenidos, una Elastic IP sin uso, NAT Gateway y
logs también pueden cobrar. La destrucción ejecutada eliminó los recursos de
la práctica; aun así, la cuenta debe revisarse por recursos ajenos o cargos
rezagados. Para consultar Billing/Cost Explorer, use root solo si la política
de la cuenta lo exige; `user_cli` es la identidad de las operaciones normales.

## Comparación

| Herramienta | Ventaja comprobable en esta práctica | Coste operativo/riesgo |
|---|---|---|
| Terraform | Mantiene estado y grafo; `plan` permite revisar cambios y `destroy` expresa la limpieza declarativamente. | Hay que proteger el estado, revisar el plan y conservar coherencia entre estado y cuenta. |
| Boto3 | Permite lógica Python, clientes reutilizados, waiters y manejo explícito de respuestas. | El código debe capturar IDs, ordenar dependencias y cubrir errores/interrupciones. |
| AWS CLI | Expone cada llamada y es fácil de auditar en una secuencia de comandos. | Requiere capturar IDs, ordenar manualmente la destrucción y cuidar parámetros/shell. |

En los tres casos RDS gestionó la contraseña mediante Secrets Manager; el código
no imprimió ni guardó su valor. Las tres variantes produjeron la misma clase de
recursos, pero sus evidencias reflejan estados transitorios distintos: por
entonces RDS estaba `creating` en la verificación CLI y `available` en las
verificaciones de Terraform y Boto3.

## Equivalentes manuales en AWS Console

Estos pasos reproducen la arquitectura del laboratorio sin scripts. Inicie
sesión en la región **Ohio (`us-east-2`) como `user_cli`**. Use nombres y CIDR
consistentes, etiquete recursos con `Project=EIA-AWS-Activity`,
`Environment=Lab` y `ManagedBy=OMP`, y espere los estados indicados antes de
continuar. Root se reserva únicamente para auditoría de Billing/Cost Explorer.
No copie valores de contraseñas a formularios, capturas o evidencias.

### 1. S3

1. En **S3 → Buckets → Create bucket**, elija `us-east-2`, un nombre globalmente
   único y mantenga el acceso público bloqueado.
2. En **Properties**, habilite el cifrado del lado del servidor con SSE-S3
   (`AES256`). Configure Lifecycle para expirar objetos a los siete días si la
   prueba lo requiere.
3. En **Objects**, cargue `dataset.csv`. Verifique que el bucket responde y que
   el bloqueo de acceso público sigue activo.
4. Para limpiar, elimine primero los objetos y luego el bucket.

### 2. VPC, subredes, ruta, IGW y security groups

1. En **VPC → Your VPCs → Create VPC**, cree una VPC IPv4 `10.42.0.0/16` y
   active DNS resolution y DNS hostnames.
2. En **Internet gateways**, cree un IGW y adjúntelo a esa VPC.
3. En **Subnets**, cree una subred pública `10.42.1.0/24` en una AZ disponible
   y dos privadas (`10.42.10.0/24` y `10.42.11.0/24`) en dos AZ disponibles.
   Active la asignación automática de IPv4 pública solo en la subred pública.
4. En **Route tables**, cree una tabla para la subred pública, agregue
   `0.0.0.0/0` hacia el IGW y asóciela con la subred pública. Mantenga las
   subredes privadas sin ruta NAT: el diseño no usa NAT Gateway.
5. En **Security groups**, cree uno para EC2 con TCP 22 desde
   `trusted_cidr` (un `/32` controlado) y otro para RDS con TCP 5432 cuyo origen
   sea el security group de EC2. No abra estas reglas a todo Internet.
6. Para limpiar, elimine primero asociaciones/rutas dependientes y security
   groups, desadjunte y elimine el IGW, elimine subredes y finalmente la VPC.

### 3. EC2

1. En **EC2 → Instances → Launch instance**, seleccione Amazon Linux 2023
   x86_64, tipo `t3.micro`, la VPC creada, la subred pública y el security group
   de EC2. Seleccione una clave existente solo si se usará SSH.
2. En almacenamiento, use el volumen raíz gp3 de 8 GiB, cifrado y con
   **Delete on termination**. En configuración avanzada de metadatos, marque
   **IMDSv2 required** (`HttpTokens=required`).
3. Etiquete la instancia y espere el estado `Running`; la evidencia no supone
   que se haya abierto una sesión SSH.
4. Para limpiar, termine la instancia y espere `Terminated`. AWS puede conservar
   su registro histórico por ID aunque ya no esté activa.

### 4. RDS PostgreSQL

1. En **RDS → Subnet groups**, cree un subnet group con las dos subredes
   privadas.
2. En **Databases → Create database**, elija PostgreSQL 16, plantilla de
   laboratorio/dev-test, clase `db.t3.micro`, Single-AZ, 20 GiB gp3 y cifrado.
   Desactive acceso público, seleccione el subnet group y el security group de
   RDS. Use retención de backups de 0 días y sin deletion protection para esta
   práctica.
3. En credenciales, seleccione **Manage master credentials in AWS Secrets
   Manager**. No lea, copie ni imprima el valor. Espere `Available` y verifique
   que la instancia no es pública.
4. Para limpiar, elimine la instancia sin snapshot final solo para este
   laboratorio, espere a que termine, elimine el subnet group y compruebe que no
   quedó un secreto administrado o backup que deba cobrarse.

### 5. Secrets Manager

RDS crea y administra automáticamente el secreto cuando se selecciona la opción
anterior. En **Secrets Manager → Secrets**, como `user_cli`, compruebe únicamente
los metadatos del secreto asociado a RDS (nombre/ARN y fecha), sin seleccionar
**Retrieve secret value**. La consola puede impedir borrar directamente un
secreto administrado por RDS mientras la base exista; elimine primero RDS y
vuelva a comprobar su estado según la política de retención de la cuenta. La
operación normal de la práctica no requiere root.

## Verificación y límites

Antes de crear, confirme identidad, región y disponibilidad de
`db.t3.micro`/PostgreSQL 16 en `us-east-2`. Después de cada destrucción,
verifique S3 con `head-bucket`, RDS con `describe-db-instances`, VPC con
`describe-vpcs` y recursos EC2 activos con una consulta de estado, además de
revisar etiquetas, volúmenes, NAT, interfaces y secretos. Las evidencias de
esta ejecución son las enlazadas en la tabla inicial; no describen recursos de
otras prácticas de la cuenta.
