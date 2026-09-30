# Checklist de auditoría y cleanup AWS

Checklist genérico para la región `us-east-2`. Sustituir los marcadores localmente; no guardar ARN, contraseña, token ni salida sensible en el repositorio.

## Antes de crear

- [ ] Confirmar identidad y región:

  ```bash
  aws sts get-caller-identity --query Arn --output text
  aws configure get region
  ```

  **Esperado:** identidad `user_cli` y `us-east-2`. La cadena estándar de credenciales puede resolver esa identidad; no asumir un perfil llamado `user_cli`.

- [ ] Confirmar que el nombre y las etiquetas distinguen el punto (`Project=EIA-AWS-Activity`, `Environment=Lab`, `Point=N`).
- [ ] Revisar el plan o `dry-run` antes de `--execute`.
- [ ] Confirmar que los CIDR de administración son `/32` y que los secretos se introducen de forma interactiva o desde Secrets Manager.

## Durante la ejecución

- [ ] Registrar solo IDs, estados, conteos y timestamps saneados.
- [ ] Esperar estados operativos antes del workload: EC2 `running`, RDS/DocumentDB/Neptune `available`, y el estado de Redshift que indique la API.
- [ ] No registrar `SecretString`, contraseñas, tokens, endpoints privados ni claves privadas.
- [ ] Si un recurso queda `MODIFYING`, `CREATING` o en otro estado transitorio, detener el workload y seguir el cleanup del wrapper; no presentarlo como resultado funcional.

## Auditoría genérica posterior

Usar filtros por tags, prefijos o IDs conocidos del punto. Estos comandos son plantillas y no deben ejecutarse con valores inventados:

```bash
aws ec2 describe-instances \
  --filters 'Name=instance-state-name,Values=pending,running,stopping,stopped' \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Tags:Tags}'
aws ec2 describe-volumes --filters Name=status,Values=available,in-use
aws ec2 describe-network-interfaces --filters Name=status,Values=available,in-use
aws ec2 describe-addresses --query 'Addresses[].{AllocationId:AllocationId,PublicIp:PublicIp,InstanceId:InstanceId}'
aws ec2 describe-nat-gateways --filter Name=state,Values=pending,available,deleting
aws s3api list-buckets --query 'Buckets[].Name'
aws rds describe-db-instances --query 'DBInstances[].{Id:DBInstanceIdentifier,Status:DBInstanceStatus}'
aws docdb describe-db-clusters --query 'DBClusters[].{Id:DBClusterIdentifier,Status:Status}'
aws neptune describe-db-clusters --query 'DBClusters[].{Id:DBClusterIdentifier,Status:Status}'
aws secretsmanager list-secrets --query 'SecretList[].{Name:Name,Arn:ARN}'
```

Para Redshift Serverless:

```bash
aws redshift-serverless list-workgroups
aws redshift-serverless list-namespaces
```

Para S3, auditar primero los objetos del bucket propio y luego el bucket:

```bash
aws s3api list-objects-v2 --bucket '<BUCKET_TEMPORAL>' --query 'Contents[].Key'
aws s3api head-bucket --bucket '<BUCKET_TEMPORAL>'
```

**Estados esperados después de limpiar:** listas vacías para los recursos y prefijos del punto; ningún recurso en ejecución; ningún objeto en el bucket temporal; secretos ausentes o en el estado de eliminación documentado; ENI, EBS, NAT, EIP, subnet groups, snapshots y resultados auxiliares revisados.

## Orden recomendado

1. Detener workloads, crawlers y consultas pendientes.
2. Eliminar instancias o workgroups antes de clusters/namespaces.
3. Eliminar bases de datos y subnet groups cuando ya no tengan dependencias.
4. Vaciar y eliminar buckets S3, incluidos resultados de Athena.
5. Eliminar secretos temporales y roles creados exclusivamente para el punto, respetando dependencias.
6. Eliminar EC2, EBS, security groups, subredes, rutas, IGW y VPC cuando pertenezcan al punto.
7. Auditar snapshots, backups, EIP, NAT, ENI, logs y secretos retenidos.
8. Revisar Billing/Cost Explorer si la política de la cuenta lo permite.

El orden exacto puede variar por dependencias; seguir primero el README y el script de cleanup del punto. Nunca borrar un role o recurso compartido solo porque aparece en una búsqueda amplia.

## Limitaciones observadas

- DocumentDB: Compass sí conectó, pero mostró warning de validación TLS desactivada; Python validó la CA de AWS de forma independiente.
- Neptune: la ejecución real usó endpoint público como excepción temporal, restringido a `201.221.176.28/32`, TLS e IAM. No convertir ese patrón en configuración permanente.
- Redshift: el workgroup manual `eia-p5-manual-wg` terminó `AVAILABLE`; el workload IAM observó filtro de 3 filas, JOIN de 5 y agregación de 6. Los recursos temporales quedaron eliminados; el workgroup manual se conserva.
- Glue/Athena: ejecución real completada; filtro de 9 filas, GROUP BY de 4, append/update `SUCCEEDED` y cleanup verificado. `state.json` se eliminó antes de entregar.
