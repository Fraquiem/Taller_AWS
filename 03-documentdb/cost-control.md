# Control de costos (pre-despliegue)

No se ha creado ningún recurso. La configuración selecciona DocumentDB
Serverless v2 (`db.serverless`) con `0.5`–`1.0` DCU y `storage_type =
"standard"`. Las cifras siguientes son evidencia de planificación, no una
factura; volver a confirmar `us-east-2` antes de `apply` y guardar la consulta
en `evidence/cost-before.json`.

Fuentes oficiales:

- [DocumentDB pricing](https://aws.amazon.com/documentdb/pricing/)
- [EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- [Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)
- [DocumentDB Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html)

## Evidencia regional y comparación

La consulta de precios de **us-east-2 (Ohio)** con vigencia publicada
**2026-06-01** reporta:

| Componente | Tarifa regional | Fórmula |
|---|---:|---|
| DocumentDB Serverless Standard | USD 0.0822/DCU-h | `H × DCU_promedio × 0.0822` |
| Serverless mínimo configurado | USD 0.0411/h | `H × 0.5 × 0.0822` |
| DocumentDB provisioned `db.t3.medium` | USD 0.078/instance-h | `H × 0.078` |

Para 4 horas, el cómputo DocumentDB sería USD 0.1644 al mínimo Serverless
frente a USD 0.312 aprovisionado. Se elige Serverless porque la práctica es
corta y su piso de capacidad reduce el costo fijo; el máximo de 1 DCU limita
el consumo accidental. La comparación no incluye almacenamiento, I/O,
backup, transferencia, bastión/EBS, IP pública ni Secrets Manager.

Fuentes oficiales: [DocumentDB pricing](https://aws.amazon.com/documentdb/pricing/),
[EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/),
[Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/) y
[AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html).

## Variables y cifras adicionales

| Variable | Valor de planificación | Unidad/fuente |
|---|---:|---|
| `U` | `0.0822` | USD/DCU-h, Serverless Standard us-east-2 |
| `D` | `0.078` | USD/instance-h, `db.t3.medium` us-east-2 |
| `E` | `0.0104` como referencia histórica | USD/instance-h, EC2 `t3.micro`; confirmar |
| `S` | `0.40` | USD/secret-month, Secrets Manager; confirmar |
| `A` | `0.05` por 10.000 llamadas | USD, Secrets Manager API; confirmar |
| `G` | cotización de almacenamiento DocumentDB | USD/GB-month |
| `I` | cotización de I/O DocumentDB | USD/million requests |

No asumir que las tarifas permanecen constantes: registrar fecha, región,
SKU/modalidad y respuesta de Price List. Si se compara aprovisionado, usar
`D`; para esta plantilla usar `U × DCU_promedio`.

## Escenarios aprobables

Para una prueba de `H=4` horas, capacidad Serverless media `C=0.5` DCU, un
bastión y `B=1 GB` de almacenamiento, `N=100` llamadas Secrets Manager y sin
tráfico significativo:

```text
docdb_serverless = H × C × U
compute           = docdb_serverless + H × E
secret            = S × H / 730          # aproximación; confirmar facturación parcial
api               = ceil(N / 10_000) × A
storage           = G × B × H / 730      # aproximación; confirmar mínimo/facturación
subtotal           = compute + secret + api + storage + I/O + backup + transferencia
```

Con `U=0.0822`, `C=0.5` y `E=0.0104`, el cómputo conocido para 4 horas es
`4 × (0.0411 + 0.0104) = USD 0.206`; el bastión por sí solo agrega
`4 × 0.0104 = USD 0.0416`, antes de EBS/IP/transferencia. No publicar un
total final hasta confirmar `G` e `I`.

Para 8 horas, el bastión agrega USD 0.0832 con la misma referencia. Destruir
inmediatamente es obligatorio: mientras están activos cobran Serverless o
instancia, EC2, EBS y los demás componentes.

## Cleanup y cargos idle

`terraform destroy` elimina cluster, instancia, VPC, SG, subnets, bastión, EBS y secreto administrado por Terraform. El key pair no es un recurso Terraform: `cleanup.sh` ejecuta `delete-key-pair` y elimina la clave local de `/tmp`. Verificar snapshots, EIP, volúmenes y versiones del secreto; si se requiere, `FORCE_DELETE_SECRET=1` elimina el secreto sin ventana de recuperación. No dejar DocumentDB, EC2, EBS, IP o secreto durante la noche.
