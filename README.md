# Centinela — Semana 1

Repositorio de la célula para la Semana 1 de Centinela (ver
`Azure-Semana1.md` para el alcance completo). Este README cubre lo que
corresponde a **Persona 4** (contrato, API de ingesta, documentación): cómo
correr y probar la API localmente, y cómo se conecta con la infraestructura
que aprovisionan las Personas 1, 2 y 3.

> **Estado:** las secciones marcadas `[PENDIENTE]` dependen de entregables
> de otras personas del equipo (script de aprovisionamiento, red, identidad
> gestionada) que aún no están integrados en este repositorio. El objetivo
> final del entregable 26 ("un tercero clona el repositorio y levanta el
> sistema siguiendo exclusivamente este README") no se cumple todavía de
> punta a punta — solo la parte de la API.

## 1. Estructura del repositorio

```
Azure-Semana1.md          Especificación de la semana
docs/                      Documentación (contrato, decisiones, costos, etc.)
api/
  app/
    main.py                Punto de entrada FastAPI + manejo de errores
    core/config.py         Configuración externalizada (variables de entorno)
    models/transaction.py  Contrato de la transacción
    api/routes.py          Capa HTTP (delgada)
    services/ingestion.py  Orquestación: validar -> idempotencia -> persistir -> [publicar]
    storage/                Persistencia (memoria / Azure Blob), detrás de una interfaz
    messaging/publisher.py Publicación de eventos (No-Op en semana 1, punto de inserción semana 2)
  tests/                    Suite de pruebas (pytest), corre sin Azure
  requirements.txt
```

## 2. Correr la API en local (sin Azure)

Requiere Python 3.11+.

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

Por defecto usa el backend de almacenamiento en memoria
(`CENTINELA_STORAGE_BACKEND=memory`), no requiere ninguna credencial de
Azure. Los datos se pierden al reiniciar el proceso — es solo para
desarrollo y para las pruebas de validación de contrato.

Probar la API:

```bash
curl -X POST http://localhost:8000/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "account_id": "acc-001",
    "amount_minor_units": 1500,
    "currency": "USD",
    "client_timestamp": "2026-07-22T12:00:00Z",
    "location": {"latitude": 4.6097, "longitude": -74.0817},
    "merchant": {"merchant_id": "merch-001", "category": "grocery"}
  }'

curl http://localhost:8000/transactions/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

## 3. Correr las pruebas

```bash
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v
```

Las pruebas cubren: aceptación de una transacción válida, rechazo de cada
tipo de payload inválido descrito en la sección 2.9, comportamiento
idempotente ante duplicados, que las respuestas de error no filtran
detalles internos, y recuperación por identificador.

## 4. Configuración (variables de entorno)

Prefijo `CENTINELA_`. Ver `api/app/core/config.py` para el detalle completo.

| Variable | Valores | Por defecto | Notas |
|---|---|---|---|
| `CENTINELA_STORAGE_BACKEND` | `memory` \| `blob` | `memory` | `blob` requiere `CENTINELA_BLOB_ACCOUNT_URL` |
| `CENTINELA_BLOB_ACCOUNT_URL` | URL de la cuenta de storage | — | p. ej. `https://<cuenta>.blob.core.windows.net` |
| `CENTINELA_BLOB_CONTAINER_RAW_TRANSACTIONS` | nombre de contenedor | `raw-transactions` | Debe existir de antemano (lo crea el script de aprovisionamiento) |
| `CENTINELA_EVENT_PUBLISHER_BACKEND` | `noop` | `noop` | En semana 2 se añade un backend real |
| `CENTINELA_MAX_AMOUNT_MINOR_UNITS` | entero | `10000000` | Monto máximo aceptado, en unidad monetaria menor |
| `CENTINELA_CLOCK_SKEW_TOLERANCE_SECONDS` | entero | `60` | Tolerancia para rechazar `client_timestamp` futuro |

En Azure estos valores se configuran como *Application Settings* del App
Service (sección 2.9: "configuración... gestionada mediante la
configuración de la aplicación"), no en archivos de código.

## 5. Despliegue en Azure `[PENDIENTE]`

Pasos que faltan documentar aquí una vez estén listos los entregables de
las otras personas:

- **`[PENDIENTE — Persona 1]`** Comando(s) del script de aprovisionamiento
  para crear el grupo de recursos, el App Service Plan (Basic B1, ver
  `docs/nivel-servicio-costo.md`) y la Web App.
- **`[PENDIENTE — Persona 2]`** Cómo se asigna la identidad gestionada del
  rol Servicio a esta Web App y qué permisos concretos necesita sobre el
  contenedor `raw-transactions` (mínimo: `Storage Blob Data Contributor`
  sobre ese contenedor específico — sin permisos de plano de control).
- **`[PENDIENTE — Persona 3]`** Nombre/rango de la subred de aplicación a
  la que se integra esta Web App (`az webapp vnet-integration add`), y
  nombre real de la cuenta de storage y el contenedor a usar en
  `CENTINELA_BLOB_ACCOUNT_URL` / `CENTINELA_BLOB_CONTAINER_RAW_TRANSACTIONS`.
- Comando de despliegue del código de `api/` a la Web App (p. ej.
  `az webapp up` o pipeline de CI/CD) — a definir.

**Autenticación con Azure Blob Storage:** exclusivamente vía
`DefaultAzureCredential` (identidad gestionada). No se generan ni se
distribuyen claves de cuenta ni connection strings — coherente con los
requerimientos 2.6 y 2.10.

## 6. Documentación relacionada

- `docs/contrato-transaccion.md` — contrato completo y las 4 decisiones justificadas.
- `docs/clasificacion-componentes.md` — modelo de servicio de cada componente del sistema.
- `docs/nivel-servicio-costo.md` — justificación del App Service Plan y costo estimado.
- `docs/codigos-estado.md` — tabla de códigos HTTP por escenario.
- `docs/idempotencia.md` — estrategia de idempotencia.
- `docs/decisiones-arquitectura.md` — registro de decisiones de arquitectura (abierto a las 4 personas).
