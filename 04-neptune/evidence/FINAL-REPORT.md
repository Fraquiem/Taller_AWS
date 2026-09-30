# Evidencia final — Punto 4 (Amazon Neptune)

Este documento resume la ejecución real del workload y enlaza los artefactos JSON
sanitizados. La ejecución ocurrió en `us-east-2`; los identificadores y el endpoint
se conservan solo donde ya están anonimizados o redactados. No se almacenan
credenciales, tokens ni secretos.

## Resultado verificable

| Comprobación | Resultado | Fuente |
|---|---:|---|
| Vértices cargados | **10** | [`workload.json`](./workload.json) |
| Relaciones cargadas | **15** | [`workload.json`](./workload.json) |
| Traversals openCypher | **3**: `people_and_courses`, `skill_reachability`, `team_to_course` | [`workload.json`](./workload.json) |
| Mínimos del ejercicio | `minimums_met: true` | [`workload.json`](./workload.json) |
| Cluster/instancia | `available` durante la prueba | [`infrastructure.json`](./infrastructure.json) |
| Motor/clase | Neptune `1.4.8.0`, `db.t3.medium` | [`infrastructure.json`](./infrastructure.json) |
| TLS y autenticación IAM | Activados (`true`) | [`preflight.json`](./preflight.json), [`infrastructure.json`](./infrastructure.json) |

Los resultados de las tres consultas están incluidos en `sanitized_results`. La
sanitización elimina endpoint, host, URI y campos de autorización o secreto.

## Elección y acceso

Se eligió **Neptune provisioned** con un escritor `db.t3.medium`: la capacidad es
predecible para una sesión de laboratorio de varias horas y, según la estimación
usada, cuesta menos que el mínimo Serverless durante ese intervalo. Serverless no
es escala-a-cero: mantiene un mínimo de 1 NCU.

El endpoint de esta ejecución fue **público de forma temporal**, con ingreso TCP
8182 limitado a `201.221.176.28/32`; no se abrió `0.0.0.0/0`. Se mantuvieron TLS,
autenticación IAM de Neptune y cifrado de almacenamiento. El endpoint se redactó
en la evidencia y no debe copiarse a documentación, capturas o commits.

Para un entorno normal, la alternativa recomendada es mantener Neptune privado y
acceder mediante:

1. una EC2 bastion en subnet pública, con SG de SSH únicamente desde un CIDR /32,
   túnel local hacia `Neptune:8182`, rol IAM e IMDSv2; o
2. preferentemente, una instancia administrada por **SSM** en subnet privada y
   `AWS-StartPortForwardingSessionToRemoteHost`, usando endpoints VPC de SSM,
   EC2 Messages y SSMMessages y permisos de sesión.

Ninguna bastion ni sesión SSM fue creada en esta ejecución. El acceso público /32
fue una excepción controlada para ejecutar desde la máquina local; no constituye
una configuración permanente.

## Coste estimado de capacidad

Son cálculos de cómputo, no una factura: no incluyen almacenamiento, I/O, backup,
transferencia, CloudWatch, NAT ni otros cargos. Se usaron las referencias de
`us-east-2`: provisioned `db.t3.medium` **USD 0.098/h** y Neptune Serverless
mínimo de 1 NCU **USD 0.16/h**.

| Opción | 4 horas | 8 horas |
|---|---:|---:|
| Neptune provisioned (`0.098 × h`) | **USD 0.392** | **USD 0.784** |
| Neptune Serverless mínimo (`0.16 × h`) | **USD 0.64** | **USD 1.28** |
| Bastion EC2 `t3.micro` de referencia (`≈0.0104 × h`) | USD 0.0416 | USD 0.0832 |
| Provisioned + bastion | USD 0.4336 | USD 0.8672 |
| Serverless + bastion | USD 0.6816 | USD 1.3632 |

El costo real depende de región, duración y cargos adicionales. La forma de
controlarlo es fijar una ventana de laboratorio y ejecutar cleanup inmediatamente.

## Limpieza y residuos

[`cleanup.json`](./cleanup.json) registra `cleanup_verified: true`. Después de la
prueba se eliminaron la instancia y el cluster Neptune, el subnet group, el SG, la
política IAM temporal y los recursos auxiliares de red. También se verificó la
limpieza de posibles residuos de intentos fallidos, incluidos IGW: el conteo de
IGW etiquetados quedó en **0**. La comprobación completa quedó en cero para:

- clusters e instancias Neptune;
- subnet groups y security groups etiquetados;
- IGW etiquetados, EIP, NAT gateways y ENI etiquetados.

El `deployment-state.json` temporal se eliminó tras cleanup y no forma parte de
los artefactos finales.

## Reproducción sin secretos

Los scripts tienen dry-run/preflight y no requieren escribir secretos en el
repositorio. Para una ejecución real, conservar el endpoint únicamente en la
shell local y borrar recursos incluso si el workload falla:

```bash
cd 04-neptune
export AWS_REGION=us-east-2
/tmp/neptune-venv/bin/python deploy.py
/tmp/neptune-venv/bin/python neptune_workload.py --execute --endpoint '<endpoint-local-no-commit>'
/tmp/neptune-venv/bin/python cleanup.py
```

La cadena estándar de credenciales de Boto3 firma las consultas con SigV4. No
sustituir `<endpoint-local-no-commit>` por un valor que luego se guarde en un
archivo o salida versionada.

## Evidencia fuente

- [`preflight.json`](./preflight.json): ordenabilidad, subnets, TLS/IAM, CIDR /32 e IGW preexistente.
- [`infrastructure.json`](./infrastructure.json): clase, versión, estado, acceso público y endpoint redactado.
- [`workload.json`](./workload.json): carga y resultados openCypher.
- [`cleanup.json`](./cleanup.json): verificación de cleanup y conteos de residuos.
- [`cost-before.json`](./cost-before.json): estado previo; no es una factura ni una estimación de costos.
