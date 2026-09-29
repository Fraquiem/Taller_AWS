# Control de costes — Punto 5

## Supuestos numéricos reproducibles

Estos valores son **supuestos de planificación, no una cotización**:

- Región: `us-east-2`.
- Una sesión de laboratorio de 2 horas, una vez al día durante 5 días: 10 horas.
- Capacidad inicial: mínimo de 4 RPU (`4 RPU × 10 h = 40 RPU-h`), únicamente como
  escenario de cálculo. Confirmar si el mínimo, unidad y precio cambian antes de
  desplegar.
- Datos: 18 filas y menos de 1 MiB de CSV; S3 y resultados Data API son pequeños.
- Presupuesto de control ilustrativo: USD 10 para toda la sesión, no garantía de
  precio ni de elegibilidad Free Tier.

Cálculo mecánico del escenario: `RPU-h = 4 × 2 × 5 = 40`. Coste Redshift
estimado = `40 × precio_RPU_h regional`; coste total = Redshift + S3 +
Secrets Manager + transferencia + cualquier almacenamiento/cargo de cuenta. No
se fija un importe por RPU porque el precio regional y las condiciones pueden
cambiar: consultar la página oficial inmediatamente antes de desplegar.

## Controles obligatorios

1. Aplicar tags comunes (`Project=Punto5`, `Owner=<responsable>`, `TTL=<fecha>`)
   al bucket, secreto y recursos Redshift cuando el servicio lo permita.
2. Usar Serverless solo por la duración de la prueba. No dejar un workgroup,
   namespace o capacidad configurada después del laboratorio.
3. Subir solo los tres CSV y borrar objetos antes de borrar el bucket.
4. Eliminar tablas, workgroup/namespace, secreto y role dedicado siguiendo el
   orden de `deploy-cleanup-plan.txt`; comprobar que no son compartidos.
5. Crear una alerta de presupuesto de cuenta/entorno antes de cualquier ejecución
   real y revisar Cost Explorer después. La alerta no impide por sí sola cargos.
6. Mantener el `--dry-run` como validación normal. No usar `--execute` en CI.
7. No activar logs de depuración de botocore: pueden exponer metadatos o payloads.

## Comparación de coste

- **Serverless**: apropiado para actividad intermitente porque evita mantener una
  instancia provisionada encendida entre sesiones, pero se factura el consumo
  mínimo/uso definido por el servicio y puede haber cargos mínimos. Es necesario
  comparar el tiempo real activo y la capacidad elegida.
- **Provisionado**: útil para actividad continua y capacidad predecible, pero una
  instancia puede facturar mientras está disponible aunque no haya consultas.
- **RDS**: suele ser la elección económica/operativa para OLTP pequeño y continuo;
  no es sustituto directo de un warehouse columnar para agregaciones crecientes.

No comprar Reserved Instances/Savings Plans para esta práctica corta. Cualquier
comparación debe usar la calculadora con región, capacidad, horas y almacenamiento
reales.

## Enlaces oficiales (consultar vigencia)

- [Redshift pricing](https://aws.amazon.com/redshift/pricing/)
- [Redshift Serverless pricing](https://aws.amazon.com/redshift/serverless/pricing/)
- [Redshift Serverless usage limits](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-usage-limits.html)
- [Redshift Data API](https://docs.aws.amazon.com/redshift-data/latest/APIReference/Welcome.html)
- [COPY desde S3](https://docs.aws.amazon.com/redshift/latest/dg/r_COPY.html)
- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)
- [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)
- [AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html)

Todas las cifras de este archivo son supuestos explícitos para detectar orden de
magnitud y no deben presentarse como evidencia de una factura real.
