# VerifiQ API — backend real

API de firma electrónica + KYC/AML para fintechs peruanas. Implementa los 5 puntos
de robustecimiento (firma certificada PAdES, KYC biométrico real, seguridad de
arquitectura, reemplazo de FormSubmit, cumplimiento Ley 29733).

## Bloque 🟢 — resuelto en esta iteración

- **Rate limiting real** (`slowapi`): `/kyc/verify` 20/min, `/signatures/sign`
  60/min, `/signatures/{id}/re-sign` 30/min, `/payments/charge` 10/min,
  `/pilot-leads` 5/min. La key del límite es la API key del cliente (no IP),
  así un cliente nunca afecta el límite de otro — probado explícitamente.
- **Retries con `tenacity`** en las llamadas HTTP reales de PSC, KYC, RENIEC/SUNAT
  y AML: 3 intentos con backoff exponencial, solo para errores transitorios
  (timeout, conexión, 5xx) — un 4xx nunca se reintenta porque repetir un
  request que el proveedor ya rechazó no tiene sentido. Pagos queda **sin**
  retry automático a propósito (ver comentario en `payments_adapter.py`):
  reintentar un cobro es más peligroso que fallarlo una vez.
- **Logging estructurado en JSON** (`app/core/logging_config.py`) + **Sentry
  opcional** vía `SENTRY_DSN`. Sin Sentry configurado, sigue funcionando
  normal, solo no manda alertas de errores en producción.
- **CI** (`.github/workflows/tests.yml`): corre `pytest` + un smoke test de
  las migraciones contra Postgres real en cada push/PR.
- **Panel interno de solo lectura** en `/panel` (servido como estático desde
  `app/static/admin.html`): lista clientes (con admin token) y, por cliente,
  sus firmas y verificaciones KYC (con la API key de ese cliente). No es un
  panel admin completo con roles — es lo mínimo para no tener que entrar
  directo a la base de datos.
- **Versionado de firmas re-firmadas**: `POST /signatures/{id}/re-sign` crea
  una nueva fila (nunca edita la original) con `version` incremental y
  `parent_signature_id`. `GET /signatures/{id}/versions` trae la cadena
  completa. La firma original queda intacta como evidencia — probado.
- **Tipo de cambio en vivo** (`exchange_rate_adapter.py`): consulta una API
  pública, cachea 1 hora, y cae al valor hardcodeado (3.75) si la API externa
  falla — probado con el proveedor simulado como caído.

Lo único que sigue sin cubrir de la lista original es **tests de los adapters
en modo "real"** — no aplica sin credenciales reales de cada proveedor,
así que solo se puede (y se hizo) testear exhaustivamente el modo mock.

## Bloque 🟡 — resuelto en esta iteración

- **`usage.py` portable a Postgres**: se quitó `strftime` (solo SQLite), ahora
  usa un rango de fechas explícito (`BETWEEN`) que funciona igual en ambos motores.
- **Endpoints de listado**: `GET /clients` y `GET /clients/{id}` (admin),
  `GET /signatures` y `GET /kyc` (por cliente, siempre filtrado a su propio
  `client_id` — probé explícitamente que un cliente no ve firmas de otro).
- **Pricing de Growth real**: portada la fórmula exacta de `updateCalc()` del
  landing (S/399 base + excedente sobre 1,000 operaciones incluidas, a precio
  promedio con 30% de descuento) a `usage.py`. Antes estaba simplificado a
  un cálculo que literalmente no hacía nada (`399 * 3.75 / 3.75`).
- **Notificaciones a ops**: cuando un KYC cae en `manual_review` (por AML
  flagged, liveness fallido, o RENIEC no coincide), se dispara
  `notifications_adapter.notify_ops()`. En mock, va a logs; con
  `NOTIFICATIONS_WEBHOOK_URL` seteado (Slack/Discord incoming webhook), se
  postea ahí. Una notificación fallida nunca tumba el request principal.

Lo que sigue pendiente: rate limiting, retries con `tenacity` en las llamadas
a proveedores externos, CI/CD, y logging estructurado/Sentry.

## Bloque crítico — resuelto en esta iteración

- **Auth de admin**: `POST /clients` y `POST /clients/{id}/api-keys` ahora exigen
  header `X-Admin-Token` (ver `ADMIN_API_TOKEN` en `.env`). Antes cualquiera
  podía crearse su propia API key.
- **Subida de archivos real**: `POST /uploads/selfie`, `/uploads/id-document`,
  `/uploads/document` reciben el archivo, lo mandan a `storage_adapter` y
  devuelven `storage_key` (+ `document_hash_sha256` para el caso de firma).
  Antes `/signatures/sign` y `/kyc/verify` asumían que esas referencias ya
  existían de la nada.
- **Idempotencia**: `/signatures/sign` y `/kyc/verify` aceptan un header
  `Idempotency-Key`. Si el cliente reintenta con la misma key, se devuelve la
  respuesta guardada en vez de crear un registro (y cobrar) duplicado.
- **CORS**: ya no es `*`, se configura por `CORS_ALLOWED_ORIGINS` (coma-separado).

Lo que queda pendiente del resto del diagnóstico (🟡 y 🟢) sigue siendo válido:
`usage.py` con `strftime` no portable a Postgres, sin endpoints de listado/lectura,
sin notificaciones cuando algo cae en `manual_review`, pricing de Growth
simplificado, sin rate limiting, sin retries con `tenacity`, sin CI/CD.

## Qué es real y qué es mock hoy

Todo el código de la API es real y corre (4/4 tests pasan). Lo que es **mock por
defecto** son las integraciones con proveedores externos de pago — porque
requieren credenciales y contratos que tú tienes que gestionar, no algo que se
resuelva escribiendo más código:

| Integración | Estado sin credenciales | Qué se necesita para volverlo real |
|---|---|---|
| Firma PAdES/PSC | Certificado `MOCK-...`, PDF no se firma criptográficamente | Contrato con Camerfirma o IO Digital + credenciales en `.env` |
| KYC biométrico (liveness + face match) | Score simulado (0.97, siempre pasa) | Cuenta en Incode / Mati, o AWS Rekognition activo |
| RENIEC / SUNAT | Valida "true" siempre | Convenio institucional o proveedor intermediario (Apis Perú, Factiliza) |
| AML / sanciones | Solo detecta 2 nombres de prueba | Cuenta en ComplyAdvantage (o similar) |
| Storage cifrado | Guarda en disco local `/tmp` | Bucket S3 + llave KMS + credenciales AWS |
| Pagos | Simula cobro exitoso | Cuenta Culqi/Kushki activa (Mercado Pago no implementado aún) |

Cada adapter en `app/adapters/` tiene la función real ya escrita o dejada como
`NotImplementedError` con el comentario exacto de qué falta — no son cajas negras.

## Arquitectura

```
app/
  core/       config, DB, seguridad (hash de API keys, cadena de hashes del audit log)
  models/     SQLAlchemy: clients, api_keys, signature_requests, kyc_verifications,
              audit_log (append-only), usage_events, payments, pilot_leads
  adapters/   PSC/PAdES, KYC biométrico, RENIEC/SUNAT, AML, storage S3, pagos
  routers/    /clients, /signatures, /kyc, /usage, /payments, /pilot-leads
  schemas/    Pydantic
alembic/      migraciones (incluye triggers que hacen el audit_log append-only
              a nivel de base de datos, no solo a nivel de aplicación)
tests/        incluye test que verifica que la cadena de hashes detecta
              manipulación directa en la BD, y que los triggers bloquean DELETE
```

### Seguridad de API keys
Las keys se generan una vez (`vfq_sb_...`), se muestran al cliente una sola vez,
y solo se guarda su hash SHA-256. Si la base de datos se filtra, las keys no
quedan expuestas.

### Audit log inmutable (evidencia legal)
Doble capa:
1. **Trigger de base de datos** (`alembic/versions/0002_...`): bloquea
   `UPDATE`/`DELETE` sobre `audit_log` a nivel SQL, incluso para alguien con
   acceso directo a la BD.
2. **Cadena de hashes**: cada evento incluye el hash del anterior
   (`app/core/audit.py::compute_audit_event_hash`). Si alguien logra alterar
   una fila, `verify_chain()` lo detecta.

### Reemplazo de FormSubmit.co
El formulario del landing ahora debe apuntar a `POST /pilot-leads` en vez de
`formsubmit.co` (el JS del HTML actual sigue usando FormSubmit — hay que
actualizar la URL del fetch, te lo dejo abajo). Exige `consent_privacidad=true`
explícito, cumpliendo el opt-in de la Ley N.º 29733.

## Cómo correrlo

```bash
cp .env.example .env          # ajusta lo que ya tengas contratado
pip install -r requirements.txt --break-system-packages
alembic upgrade head
uvicorn app.main:app --reload
```

Con Docker (incluye Postgres real, no SQLite):
```bash
docker compose up --build
```

Tests:
```bash
pytest tests/ -v
```

## Dependencias de Python (requirements.txt)

- **fastapi / uvicorn** — framework y servidor ASGI
- **pydantic / pydantic-settings** — validación y config por env vars
- **email-validator** — requerido por `EmailStr` (sin esto, `pydantic` truena)
- **SQLAlchemy / alembic** — ORM y migraciones
- **psycopg2-binary** — driver Postgres (para producción; SQLite no lo necesita)
- **httpx** — cliente HTTP async para llamar a los proveedores (PSC, KYC, AML, RENIEC)
- **cryptography** — primitivas usadas por pyhanko
- **pyhanko / pyhanko-certvalidator** — firma PAdES-BES/LTV real sobre el PDF
- **boto3** — S3 con SSE-KMS
- **tenacity** — reintentos con backoff para llamadas a proveedores externos (recomendado, no forzado aún en el código)
- **pytest / pytest-asyncio** — tests

## Próximos pasos sugeridos (en orden de impacto)

1. Cambiar el `fetch` del landing de `formsubmit.co` a tu propio `POST /pilot-leads`.
2. Contratar el proveedor de KYC biométrico (Incode es el más rápido de integrar en LatAm) — desbloquea el punto más caro de simular bien.
3. Definir con qué PSC vas a trabajar para firma certificada — esto es lo que más tiempo de negociación toma, conviene arrancarlo ya aunque el código quede mock mientras tanto.
4. Activar Culqi (es el más simple de los tres) para dejar de depender de links de Plin manuales.
5. Migrar de SQLite a Postgres antes de cualquier piloto con datos reales (los triggers de `audit_log` ya están escritos para ambos dialectos).
