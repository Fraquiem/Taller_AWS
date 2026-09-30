# Control de costos del taller

Todas las estimaciones corresponden a **`us-east-2`**, son hipotéticas y sirven para planear una ventana corta. Las tarifas, mínimos de facturación, créditos, impuestos y Free Tier cambian: consultar las páginas oficiales antes de cada ejecución. Ninguna cifra de esta guía es una factura ni un cargo observado salvo donde el README del punto enlaza evidencia explícita.

## Estimaciones por punto

| Punto | Configuración de referencia | Estimación orientativa | Cargos que pueden continuar |
|---|---|---:|---|
| 1 — Secrets Manager | Un secreto temporal, pocas lecturas y una actualización | USD 0.40/secreto-mes y USD 0.05/10.000 llamadas API; para una sesión corta, fracción de centavo | Secreto retenido, llamadas API y una eventual Lambda/KMS adicional |
| 2 — Terraform/Boto3/CLI | Una variante a la vez: EC2 `t3.micro`, RDS `db.t3.micro`, EBS 8 GiB, RDS 20 GiB y secreto | Aproximadamente **USD 0.033/h** o **USD 5.54/168 h por variante**, antes de impuestos; repetir tres variantes puede multiplicar la ventana | EC2/RDS ociosos, EBS, S3, secreto, snapshots/backups, EIP, NAT y logs |
| 3 — DocumentDB | Serverless `0.5–1.0` DCU, bastión EC2 `t3.micro`, EBS y secreto | Referencia registrada: mínimo DocumentDB USD 0.0411/h; con bastión, cómputo conocido USD 0.0515/h; unas 4 h: **USD 0.206** antes de almacenamiento, I/O y red | Cluster/instancia, almacenamiento, I/O, backups, bastión/EBS, IP, transferencia y secreto |
| 4 — Neptune | Writer provisioned `db.t3.medium`; acceso temporal público restringido; sin bastión en la ejecución observada | Referencia del README: USD 0.098/h; 4 h **USD 0.392**, 8 h **USD 0.784**, antes de almacenamiento, I/O y red. Serverless mínimo comparativo: USD 0.16/h | Capacidad provisionada o NCU mínima, almacenamiento, backup, transferencia, CloudWatch, EBS/NAT si se agregan |
| 5 — Redshift | Workgroup Serverless manual `eia-p5-manual-wg`, 4 RPU, S3 y role COPY temporales | El workgroup quedó `AVAILABLE`; el workload observó 3 filas de filtro, 5 de JOIN y 6 de agregación. El cargo depende de RPU y duración; no se presenta como factura | Workgroup/namespace manual, S3, role temporal y cualquier recurso auxiliar |
| 6 — Glue/Athena | CSV pequeño en S3, dos corridas de crawler y consultas Athena | Ejecución real observada; filtro 9 filas, GROUP BY 4 filas, append/update `SUCCEEDED`. El costo depende de DPU, duración, bytes, requests y resultados | Crawler, catálogo/metadatos, objetos y resultados S3, solicitudes y consultas Athena |

Las cifras de los puntos 1–4 provienen de los README y archivos `cost-control.md` de cada carpeta. Los puntos 5 y 6 tienen evidencia real de ejecución, pero los valores anteriores son resultados operativos y no cargos de Billing.

## Reglas prácticas

1. Usar una sola región y una ventana explícita; crear el recurso justo antes de la prueba y eliminarlo al terminar.
2. Elegir la capacidad mínima compatible con el objetivo, sin describir un servicio como “gratis” ni asumir escala a cero.
3. Evitar NAT Gateway, Multi-AZ, snapshots finales, EIP, endpoints y logging adicional salvo que el punto los requiera.
4. Vaciar S3 antes de borrar buckets; eliminar resultados de Athena y revisar secretos con ventana de recuperación o eliminación aprobada.
5. Auditar snapshots, backups, EBS, ENI, IP elásticas, NAT, roles y secretos después del cleanup. Ver el [checklist de auditoría](aws-cleanup-verification.md).
6. Separar el costo del servicio de los costos de red, almacenamiento, solicitudes, transferencia, API y retención.
7. Registrar fecha, región, modalidad, SKU, capacidad, duración y supuestos al consultar precios. Recalcular si cambia cualquiera de ellos.

## Fuentes oficiales

- [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)
- [Amazon EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- [Amazon RDS for PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/)
- [Amazon DocumentDB pricing](https://aws.amazon.com/documentdb/pricing/)
- [Amazon Neptune pricing](https://aws.amazon.com/neptune/pricing/)
- [Amazon Redshift pricing](https://aws.amazon.com/redshift/pricing/)
- [AWS Glue pricing](https://aws.amazon.com/glue/pricing/)
- [Amazon Athena pricing](https://aws.amazon.com/athena/pricing/)
- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)

La revisión de Billing/Cost Explorer debe hacerse con la autorización de la cuenta. La identidad operativa del taller es `user_cli`; no se debe inferir que un perfil local con ese nombre exista.
