# Punto 1 — AWS Secrets Manager

## Objetivo

AWS Secrets Manager es el servicio administrado que permite guardar y recuperar valores sensibles para que una aplicación no tenga que incluirlos en su código fuente. En este punto se usó para almacenar un secreto de prueba y leerlo desde Python con Boto3.

Un secreto puede contener, por ejemplo:

- credenciales de una aplicación (usuario y contraseña);
- claves o tokens de API;
- cadenas de conexión y otros parámetros confidenciales;
- material sensible en texto o en formato JSON.

El programa de este repositorio espera un objeto JSON y solo imprime metadatos no sensibles: las claves presentes, el hash SHA-256 del objeto y la etapa de versión. Nunca imprime el valor del secreto.

## Conceptos y flujo

Conviene distinguir estas operaciones:

1. **Crear:** registra un secreto y su valor inicial.
2. **Leer:** la aplicación solicita `GetSecretValue`; la autorización depende de la identidad de AWS y de una política IAM que permita leer el secreto concreto.
3. **Actualizar:** `PutSecretValue` crea una nueva versión. Una aplicación que vuelva a leer el secreto obtiene la versión marcada como `AWSCURRENT`, sin cambiar su código.
4. **Rotar:** reemplaza periódicamente el valor siguiendo un procedimiento de rotación. Puede requerir una función de rotación y credenciales/configuración adicionales. **La rotación automática no se ejecutó en esta actividad**; únicamente se actualizó manualmente el valor para comprobar el cambio de versión.

## Archivos

- [`read_secret.py`](read_secret.py): lectura con Boto3. Obtiene el identificador desde `SECRET_ID` y la región desde `AWS_REGION` (por defecto, `us-east-2`).
- [`read-only-secret-policy.json`](read-only-secret-policy.json): política mínima de lectura.
- [`evidence.json`](evidence.json): resultados observados sin valores del secreto.
- [`cost-control.md`](cost-control.md): configuración, precios consultados y limpieza.

## Permisos de lectura

La política incluida concede únicamente `secretsmanager:GetSecretValue` sobre un ARN específico:

```json
{
  "Effect": "Allow",
  "Action": "secretsmanager:GetSecretValue",
  "Resource": "arn:aws:secretsmanager:us-east-2:241732001318:secret:EIA-AWS-Activity-p1-test-secret-5LtaXK"
}
```

Ese ARN es el del secreto realmente probado y coincide con `read-only-secret-policy.json`. Para reproducir el ejercicio con otro nombre, sustituya únicamente el ARN por el que devuelva `describe-secret`; nunca use `Resource: "*"`.

La política debe adjuntarse al principal de aplicación que ejecutará el programa (por ejemplo, un usuario o un rol IAM destinado a la aplicación), siguiendo la administración IAM de la cuenta. Ejemplo para un usuario IAM; sustituya los nombres localmente y no los guarde como secretos en este repositorio:
```bash
export APP_PRINCIPAL="<usuario-de-aplicacion>"
export POLICY_NAME="ReadOnlyPoint1Secret"
aws iam put-user-policy \
  --user-name "$APP_PRINCIPAL" \
  --policy-name "$POLICY_NAME" \
  --policy-document file://read-only-secret-policy.json
```

Si el principal es un rol, use el mecanismo equivalente de IAM para adjuntar una política al rol. El usuario que ejecutó esta evidencia fue `arn:aws:iam::241732001318:user/user_cli`; esa identidad no demuestra por sí sola que la política se haya adjuntado a un principal de aplicación distinto.

## Reproducción sin publicar secretos

Los siguientes comandos reproducen el flujo en `us-east-2`. Requieren credenciales AWS configuradas mediante la cadena normal de credenciales de AWS CLI/Boto3 y permisos para las operaciones. Los valores se introducen de forma interactiva y no deben escribirse en el repositorio, en la terminal compartida ni en logs.

### 1. Crear un secreto de prueba

```bash
export AWS_REGION="us-east-2"
export SECRET_NAME="EIA-AWS-Activity-p1-repro-$(date +%s)"

read -r -s -p "JSON ficticio inicial (no se mostrará): " SECRET_JSON
printf '\n'
aws secretsmanager create-secret \
  --name "$SECRET_NAME" \
  --secret-string "$SECRET_JSON" \
  --region "$AWS_REGION" \
  --query '{ARN:ARN,Name:Name}' \
  --output table

export SECRET_ID="$SECRET_NAME"
export SECRET_ARN="$(aws secretsmanager describe-secret \
  --secret-id "$SECRET_ID" --region "$AWS_REGION" \
  --query ARN --output text)"
printf 'SECRET_ARN=%s\n' "$SECRET_ARN"
```

El ejercicio original creó el secreto `EIA-AWS-Activity-p1-test-secret` en `us-east-2`. No se documenta su valor porque no es necesario para reproducir el procedimiento.

### 2. Leer desde Python

Instale Boto3 en un entorno virtual local (el entorno `.venv/` está excluido por `.gitignore`) y ejecute:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install boto3

export SECRET_ID="$SECRET_NAME"
export AWS_REGION="us-east-2"
python 01-secrets-manager/read_secret.py
```

La salida esperada tiene esta forma, sin el valor sensible:

```json
{"keys": ["..."], "value_sha256": "...", "version_stage": "AWSCURRENT"}
```

### 3. Actualizar y volver a leer

```bash
read -r -s -p "JSON ficticio actualizado (no se mostrará): " UPDATED_SECRET_JSON
printf '\n'
aws secretsmanager put-secret-value \
  --secret-id "$SECRET_ID" \
  --secret-string "$UPDATED_SECRET_JSON" \
  --region "$AWS_REGION" \
  --query '{VersionId:VersionId,VersionStages:VersionStages}' \
  --output json

python 01-secrets-manager/read_secret.py
```

El código no cambia: la segunda lectura vuelve a pedir `GetSecretValue` y observa la versión `AWSCURRENT`.

### 4. Limpieza

Para una reproducción conservadora use un período de recuperación de siete días. El secreto queda marcado para eliminación, deja de estar disponible para la aplicación y se evita una eliminación irreversible accidental:

```bash
aws secretsmanager delete-secret \
  --secret-id "$SECRET_ID" \
  --recovery-window-in-days 7 \
  --region "$AWS_REGION" \
  --query '{ARN:ARN,DeletedDate:DeletedDate}' \
  --output json

aws secretsmanager describe-secret \
  --secret-id "$SECRET_ID" \
  --region "$AWS_REGION" \
  --query '{ARN:ARN,DeletedDate:DeletedDate}' \
  --output json
```

La ejecución documentada usó `--force-delete-without-recovery` porque era un secreto temporal creado exclusivamente para esta actividad. Inmediatamente después, `describe-secret` devolvió `DeletedDate`; una verificación posterior también puede devolver `ResourceNotFoundException`. Ambos resultados son compatibles con que no quede un secreto activo; no se debe tratar un error de recurso inexistente como fallo de limpieza.

## Resultados observados

La evidencia corresponde a la región `us-east-2` y a la identidad `arn:aws:iam::241732001318:user/user_cli`:

- Se creó `EIA-AWS-Activity-p1-test-secret` el `2026-09-29T07:17:12-05:00`.
- La primera lectura devolvió las claves `password` y `username`, con etapa `AWSCURRENT`.
- `PutSecretValue` generó la versión `1ad8b26a-788e-45b5-a607-9aaaf1752e00`.
- La lectura posterior mantuvo las claves `password` y `username` y la etapa `AWSCURRENT`, pero su hash fue distinto al de la primera lectura. Esto comprueba que el programa leyó el valor actualizado sin cambiar el código.
- Se ejecutó la eliminación forzada a las `2026-09-29T07:18:45-05:00`. La verificación posterior devolvió `DeletedDate` y no quedó un secreto activo.

Los hashes están en [`evidence.json`](evidence.json); no permiten reconstruir ni divulgan los valores originales.

## Costos y control

La estimación documentada en [`cost-control.md`](cost-control.md), para `us-east-2`, usa los precios consultados el 2026-09-29:

- USD 0.40 por secreto-mes.
- USD 0.05 por 10.000 llamadas a la API.
- Un secreto activo genera costo de almacenamiento aunque no se consulte; consultar repetidamente el mismo secreto incrementa las llamadas API, no crea secretos adicionales.
- Para una aplicación de alta frecuencia puede ser conveniente leer una vez y conservar el valor en memoria durante la vida segura del proceso, con una expiración adecuada. No debe registrarse ni persistirse innecesariamente.
- El costo horario aproximado de almacenamiento de un secreto es `0.40 / (365 × 24) = USD 0.0000457/h`. Las pocas llamadas de esta prueba representan menos de una fracción de centavo; el total real puede depender de créditos o Free Tier.
- La prueba no creó Lambda de rotación, una clave KMS administrada por el cliente, VPC, EC2 ni recursos auxiliares. El secreto usó la clave administrada por AWS para Secrets Manager.

Precios oficiales consultados: <https://aws.amazon.com/secrets-manager/pricing/>.

## Referencias de evidencia

La ejecución, los identificadores, las marcas de tiempo, los hashes y la verificación de limpieza están en [`evidence.json`](evidence.json). Este README no publica valores ficticios, contraseñas, credenciales ni claves de acceso.
