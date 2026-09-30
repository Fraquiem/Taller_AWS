# Taller AWS — Ingeniería de Datos

Repositorio educativo de la actividad AWS 2026-2. Cada carpeta numerada contiene el código, las instrucciones y la evidencia sanitizada de un punto. La región de trabajo es **Ohio (`us-east-2`)**.

## Propósito y alcance

La actividad recorre secretos, aprovisionamiento, bases de datos documentales y de grafos, analítica relacional y catálogo de datos:

1. [AWS Secrets Manager](01-secrets-manager/README.md): crear, leer y actualizar un secreto ficticio desde Python.
2. [Terraform, Boto3 y AWS CLI](02-terraform-sdk-cli/README.md): crear y destruir, secuencialmente, S3, EC2, RDS y red con tres herramientas.
3. [Amazon DocumentDB](03-documentdb/README.md): DocumentDB Serverless, túnel SSH, TLS, Compass y consultas Python.
4. [Amazon Neptune](04-neptune/README.md): grafo openCypher, autenticación IAM y acceso temporal restringido.
5. [Amazon Redshift](05-redshift/README.md): Redshift Serverless, S3, `COPY` y consultas analíticas.
6. [Glue Data Catalog + Athena](06-glue-athena/README.md): datos CSV en S3, crawler, catálogo y consultas Athena.

La [guía fuente](aws_data_engineering_activity_guide.md) define los entregables. Los enlaces a `evidence/` en cada README son la fuente de los hechos observados; los archivos de estado, secretos, claves privadas y credenciales no forman parte de la entrega.

## Estado resumido

- **Punto 5:** el workgroup manual `eia-p5-manual-wg` quedó `AVAILABLE` y se ejecutó el workload real mediante Data API con autenticación IAM. Se cargaron 5/6/7 filas en las tres tablas; filtro, JOIN y agregación terminaron correctamente. Bucket y role temporales eliminados; el workgroup manual se conservó.
- **Punto 6:** ejecución real completada y limpiada. Athena devolvió 9 filas en el filtro y 4 filas en el `GROUP BY`; append/update y dos corridas del crawler terminaron `SUCCEEDED`. La evidencia no contiene credenciales.

## Autenticación y región

Las operaciones documentadas usan la identidad real `user_cli` mediante la cadena estándar de credenciales de AWS (configuración local, variables de entorno o credenciales temporales). **No se afirma que exista un perfil llamado `user_cli`**: el nombre identifica la identidad, no una configuración concreta de `AWS_PROFILE`.

Antes de cualquier ejecución autorizada, comprobar sin exponer credenciales:

```bash
export AWS_REGION=us-east-2
aws sts get-caller-identity --query Arn --output text
aws configure get region
```

El ARN esperado debe corresponder a `user_cli` y la región a `us-east-2`. No usar la cuenta raíz para las operaciones del laboratorio. El acceso a Billing/Cost Explorer puede requerir permisos administrativos separados.

## Seguridad

- Usar Secrets Manager para contraseñas de bases de datos; no escribir valores en código, shell compartida, capturas ni evidencias.
- Mantener S3 privado y cifrado; restringir `iam:PassRole` y los roles de servicio a los recursos exactos.
- Usar security groups con orígenes `/32` o referencias a otros security groups; nunca abrir SSH o bases de datos a `0.0.0.0/0`.
- Tratar Terraform state, planes, claves privadas y tokens como información sensible.
- En DocumentDB, Compass mostró una advertencia de validación TLS desactivada, aunque Python validó la CA de AWS. La captura no demuestra validación de CA en Compass.
- Neptune usó como excepción un endpoint público temporal restringido a `201.221.176.28/32`, con TLS e IAM; para nuevos usos se recomienda acceso privado mediante SSM o bastión restringido.

## Ejecución y cleanup

Cada README describe el modo local (`dry-run`) y el modo real opt-in cuando existe. Ejecutar un solo punto a la vez, etiquetar los recursos y conservar únicamente evidencia sanitizada. Después del workload, seguir el procedimiento de cleanup del punto y consultar el [checklist de verificación](docs/aws-cleanup-verification.md). El [control de costos](docs/cost-control.md) resume las hipótesis y no reemplaza la tarifa vigente de AWS.

No se deben dejar instancias, bases de datos, buckets, objetos, secretos, snapshots, volúmenes, IP elásticas, NAT Gateway, ENI ni resultados de Athena sin revisar. La limpieza no equivale a una factura en cero: comprobar también Billing/Cost Explorer según los permisos de la cuenta.
