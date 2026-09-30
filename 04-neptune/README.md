# Punto 4 — Amazon Neptune frente a Neo4j (ejecución temporal)

Este directorio contiene el workload reproducible de **openCypher**, el despliegue
temporal Boto3 y la evidencia técnica de una ejecución real en `us-east-2`. El
despliegue usa un escritor Neptune provisioned `db.t3.medium`, endpoint público
temporal restringido a `201.221.176.28/32`, TLS y autenticación IAM. Los recursos
se eliminan inmediatamente después del workload; la evidencia no contiene endpoint
ni secretos.

## Entregables y validación local

| Artefacto | Propósito |
|---|---|
| `neptune_workload.py` | Carga 10 vértices y 15 relaciones; ejecuta 3 recorridos. Dry-run por defecto. |
| `iam-policy.json` | Referencia de permisos mínimos para consultas IAM de Neptune. |
| `deploy.py` / `deploy.sh` | Preflight y despliegue temporal Boto3 con SG /32, TLS/IAM y evidencia sanitizada. El despliegue no crea ni adjunta IGW, exige rutas públicas preexistentes, guarda estado incremental y hace rollback best-effort. |
| `cleanup.py` / `cleanup.sh` | Elimina instancia, cluster, subnet group y SG; verifica explícitamente subnet groups y ENI restantes. |
| `evidence/*.json` | Evidencia técnica sanitizada del preflight, infraestructura, workload y limpieza. |
| [`evidence/FINAL-REPORT.md`](evidence/FINAL-REPORT.md) | Informe final de la ejecución real, resultados 10/15/3, acceso, costos y cleanup verificado. |

La evidencia final se resume en [`evidence/FINAL-REPORT.md`](evidence/FINAL-REPORT.md).
Los JSON enlazados allí son la fuente verificable; no contienen endpoint ni secretos.

La ejecución real histórica se conserva intacta en `evidence/`. Para nuevas
ejecuciones, `deploy.py` exige que cada subnet elegida ya tenga una ruta
`0.0.0.0/0` hacia un Internet Gateway adjunto. Nunca crea, adjunta, reemplaza
ni añade rutas o gateways. Si falla después de crear un recurso, el estado se
escribe incrementalmente en `evidence/deployment-state.json` y se intenta un
rollback best-effort. Ejecuta cleanup aunque el rollback no sea completo:

```bash
cd 04-neptune
export AWS_REGION=us-east-2
/tmp/neptune-venv/bin/python deploy.py --dry-run
/tmp/neptune-venv/bin/python deploy.py
/tmp/neptune-venv/bin/python cleanup.py
```

`--dry-run` no crea, elimina ni consulta recursos AWS. La política IAM no se
adjunta dinámicamente durante el deploy: `iam-policy.json` es una referencia
que debe aplicar el administrador o rol del cliente, sustituyendo los
marcadores del recurso real. Así se evita derivar un nombre de usuario IAM
desde un ARN (los ARNs de roles, usuarios federados y sesiones no son
intercambiables).

Para repetir la ejecución, se debe conservar el endpoint solo en la shell local
y eliminar recursos si cualquier paso falla:

```bash
cd 04-neptune
export AWS_REGION=us-east-2
/tmp/neptune-venv/bin/python deploy.py
/tmp/neptune-venv/bin/python neptune_workload.py --execute --endpoint '<endpoint-local-no-commit>'
/tmp/neptune-venv/bin/python cleanup.py
```

La política IAM no se adjunta dinámicamente durante el deploy; `iam-policy.json`
es una referencia que debe aplicar el administrador o rol del cliente,
sustituyendo el marcador del recurso real. El endpoint no se publica en
evidencias.

El cliente debe ejecutarse desde una máquina con ruta a la VPC. El endpoint no debe
publicarse en capturas o evidencias; el programa elimina claves `endpoint`, `host`,
`uri`, `password`, `secret` y `authorization` de las respuestas.

## Elección y comparación Neptune/Neo4j

| Criterio | Neptune Database | Neo4j (Community/Enterprise/ Aura) |
|---|---|---|
| Operación | Servicio administrado AWS, almacenamiento y backups integrados | Community autogestionado o servicio Aura administrado |
| Lenguajes | openCypher, Gremlin y SPARQL | Cypher/openCypher (según edición/servicio) |
| Integración | IAM, VPC, CloudWatch y servicios AWS | Ecosistema Neo4j, drivers y herramientas propias |
| Coste de este laboratorio | Provisionado: capacidad continua; no escala a cero | VM/servicio elegido; también cobra mientras está encendido |
| Adecuación | El laboratorio ya está en AWS y necesita traversal administrado | Buena alternativa si se requiere tooling Neo4j específico o portabilidad |

Se elige Neptune provisioned de un escritor `db.t3.medium`: es un diseño pequeño,
predecible y más barato que el mínimo Serverless para una sesión de varias horas.
Neptune Database requiere VPC; Serverless tampoco es escala-a-cero: conserva una
capacidad mínima de NCU. Verificar precios y disponibilidad antes de aplicar porque
cambian por región.

## Arquitectura de acceso recomendada

```text
Laptop local
   │ SSH 22 restringido (o SSM port forwarding, sin SSH público)
   ▼
EC2 bastion t3.micro en subnet pública       IAM role + IMDSv2
   │ túnel local 127.0.0.1:8182 → Neptune:8182
   ▼
Neptune DB, 1 writer db.t3.medium, subnets privadas en 2 AZ
```

- VPC sugerida `10.80.0.0/16`; dos subnets privadas (una por AZ) para Neptune y,
  solo si se usa túnel SSH, una subnet pública para el bastion.
- Tabla privada: rutas locales a VPC; no se requiere NAT para que Neptune funcione.
  El bastion necesita salida para administración; preferir VPC endpoints de SSM,
  EC2 Messages y SSMMessages en vez de NAT cuando sea viable.
- SG del bastion: TCP/22 únicamente desde `TRUSTED_CIDR/32`; no abrir SSH a
  `0.0.0.0/0`. SG de Neptune: TCP/8182 únicamente desde el SG del bastion.
  No hay ingreso público al cluster.
- Activar TLS y autenticación IAM de Neptune. El rol del cliente recibe solo la
  política en `iam-policy.json`; el bastion no guarda secretos. La conexión Boto3
  se firma con SigV4 mediante la cadena estándar de credenciales.
- Alternativa preferida a una IP pública: instancia administrada por SSM en subnet
  privada y `AWS-StartPortForwardingSessionToRemoteHost`, o AWS Client VPN. Ambas
  eliminan el bastion público; SSM requiere endpoints privados y permisos de sesión.

### Comparación con endpoint público

Un endpoint público simplifica el acceso local, pero aumenta superficie de ataque y
no elimina la necesidad de VPC, SG, TLS e IAM. La ejecución real documentada usó
un CIDR /32, sin `0.0.0.0/0`, IAM/TLS y cierre inmediato. El acceso privado con
bastion/SSM reduce la exposición; la ejecución real usó el endpoint público
restringido únicamente como excepción temporal.

## Coste de capacidad y control de gasto

Referencias de `us-east-2` usadas para estimación (no una factura): provisioned
`db.t3.medium = USD 0.098/h`; Neptune Serverless mínimo `1 NCU = USD 0.16/h`;
bastion EC2 `t3.micro ≈ USD 0.0104/h`. Cálculo solo de cómputo:

| Escenario | 4 h | 8 h |
|---|---:|---:|
| Neptune provisioned | 0.098 × h = **USD 0.392** | **USD 0.784** |
| Bastion t3.micro | **USD 0.0416** | **USD 0.0832** |
| Total Neptune + bastion | **USD 0.4336** | **USD 0.8672** |
| Serverless mínimo (comparación) | 0.16 × h = **USD 0.64** | **USD 1.28** |
| Serverless + bastion | **USD 0.6816** | **USD 1.3632** |

Una instancia provisionada cobra también mientras está ociosa: 4/8 horas de
inactividad cuestan los mismos USD 0.392/USD 0.784 de capacidad (antes de
almacenamiento). Serverless cobra el mínimo de 1 NCU aunque no haya consultas; no
es scale-to-zero. A ambos se suman almacenamiento, I/O, backup, transferencia,
CloudWatch, EBS y posible IP pública/NAT. Para ahorrar: una sola instancia writer,
ventana explícita de laboratorio, apagar/eliminar después, límites de presupuesto
/alertas y sin NAT si endpoints SSM cubren la administración. No incluir secretos ni
state con credenciales en el repositorio.

## Ejecución real y alternativa de acceso

La ejecución real creó el cluster/instancia temporal mediante `deploy.py`, esperó
estado `available`, ejecutó `neptune_workload.py --execute` y guardó únicamente
resultados saneados. `cleanup.py` eliminó la instancia antes del cluster, la
política IAM temporal, subnet group, SG y el gateway auxiliar. También retiró
residuos de IGW de intentos fallidos y `evidence/cleanup.json` verifica cero
clusters/instancias Neptune, SG/subnet groups/IGW etiquetados, EIP, NAT o ENI.

El endpoint público fue una excepción controlada para esta prueba: SG TCP/8182
solo desde `201.221.176.28/32`, sin `0.0.0.0/0`, TLS e IAM DB authentication.
Para uso normal, una instancia EC2 privada administrada por SSM con
`AWS-StartPortForwardingSessionToRemoteHost` (o un túnel SSH local restringido a
/32) mantiene Neptune privado y evita exponer el puerto 8182.
SSM requiere endpoints privados y permisos de sesión, mientras SSH requiere SG/22
restringido y una clave o agente administrado. Ninguna alternativa se creó en esta
ejecución.

Fuentes: [Neptune User Guide](https://docs.aws.amazon.com/neptune/latest/userguide/),
[Neptune pricing](https://aws.amazon.com/neptune/pricing/),
[Neptune IAM authentication](https://docs.aws.amazon.com/neptune/latest/userguide/iam-auth.html),
y [AWS Systems Manager port forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html).
