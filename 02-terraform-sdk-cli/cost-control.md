# Informe previo de costos — punto 2

**Estado:** estimación previa; no se desplegó ningún recurso desde estos artefactos. **Región:** `us-east-2`. **Identidad prevista:** `user_cli` por la cadena estándar de credenciales. Todos los recursos llevan `Project=EIA-AWS-Activity`, `Environment=Lab`, `ManagedBy=OMP`.

## Recursos y configuración

- S3 General Purpose: un bucket, SSE-S3, bloqueo de acceso público, expiración de objetos a 7 días.
- EC2: una `t3.micro`, Amazon Linux 2023 x86_64, EBS gp3 cifrado de 8 GiB, IP pública solo para el laboratorio, IMDSv2 obligatorio.
- RDS PostgreSQL: una `db.t3.micro`, Single-AZ, 20 GiB gp3 cifrados, backups automáticos en 0 días para la prueba, sin acceso público, contraseña administrada en Secrets Manager.
- Red: una VPC, IGW, una subred pública, dos privadas, tablas de rutas y dos security groups. No hay NAT Gateway, endpoints, balanceador, Elastic IP, CloudWatch adicional ni KMS customer-managed.

## Estimación aprobable para la prueba

Precios de referencia publicados para `us-east-2` y consultados el 2026-09-29: EC2 `t3.micro` USD 0.0104/h, RDS PostgreSQL `db.t3.micro` USD 0.018/h, EBS gp3 USD 0.08/GiB-mes, RDS gp3 USD 0.115/GiB-mes, Secrets Manager USD 0.40/secreto-mes. Fuentes: [EC2 pricing](https://aws.amazon.com/ec2/pricing/on-demand/), [RDS PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/), [EBS pricing](https://aws.amazon.com/ebs/pricing/), [Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/). S3 para el dataset de prueba queda por debajo de un centavo, sujeto a requests.

| Duración | Estimación aproximada antes de impuestos |
|---|---:|
| Una hora | USD 0.033 |
| Una semana (168 h) | USD 5.54 |

El cálculo incluye `168 × (0.0104 + 0.018) = USD 4.7712` de cómputo, aproximadamente USD 0.147 de EBS, USD 0.529 de almacenamiento RDS y USD 0.092 de Secrets Manager, más S3 y requests. Se redondea a USD 5.54 antes de impuestos. No incluye créditos, Free Tier, transferencia saliente ni CPU credits por uso sostenido. Es una estimación de aprobación, no una factura.

Servicio: EC2, RDS PostgreSQL, S3, Secrets Manager y componentes VPC descritos arriba. Región: `us-east-2`. Recursos: un bucket, una EC2, una RDS y red temporal por cada variante, siempre una variante a la vez.

La configuración seleccionada es la mínima que satisface la actividad: `t3.micro`, `db.t3.micro`, almacenamiento cifrado mínimo práctico, Single-AZ, sin NAT Gateway, sin Multi-AZ, sin EIP y sin snapshot final. Costo aproximado de cada prueba: la tabla anterior durante el tiempo real de cada despliegue; la prueba completa puede sumar hasta tres veces si cada variante permanece una hora.

## Precios y cargos idle

Los precios son sujetos a la cuenta, descuentos, Free Tier, impuestos y disponibilidad regional. Consultar también: [S3 pricing](https://aws.amazon.com/s3/pricing/) y [VPC pricing](https://aws.amazon.com/vpc/pricing/).

RDS y EC2 siguen cobrando aunque no reciban tráfico; EBS y el almacenamiento S3/Secrets Manager siguen cobrando mientras existan. Backups/snapshots que sobrevivan, una Elastic IP asignada sin uso, NAT Gateway (si alguien lo agrega) y logs también pueden generar cargos. `skip_final_snapshot=true` evita un snapshot final de RDS en esta prueba; aun así, revisar snapshots y backups en la cuenta. El secreto gestionado por RDS genera el cargo de almacenamiento de Secrets Manager mientras exista.

Destruir en orden: esperar y eliminar RDS (sin snapshot final solo para este laboratorio), eliminar DB subnet group, terminar EC2, vaciar/eliminar S3, borrar security groups, rutas, subredes, IGW y VPC. Repetir verificación con APIs y revisar Cost Explorer.

