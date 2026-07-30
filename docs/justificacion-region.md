# Justificación de región

Entregable 3. Persona 1.

## 1. Región seleccionada: **West Europe (`westeurope`)**

La sección 2.2 exige justificar la región considerando **latencia**,
**disponibilidad de los servicios requeridos en las semanas 2 y 3**
(verificada, no asumida) y **costo**. El valor de región del script de
aprovisionamiento (`infra/bicep/main.bicep:6-7`) tenía originalmente
`eastus2` como default; la región efectivamente desplegada
(`infra/deploy-all.sh:15-16`) es `westeurope`. Este documento registra por
qué cambió.

## 2. Disponibilidad — el factor decisivo

Durante el primer intento de despliegue (`Fixing Bicep Budget Deployment
Errors.md`), `eastus2` falló con el error `SubscriptionIsOverQuotaForSku`
al crear el App Service Plan Linux B1. Se verificó con la API de uso real
de la suscripción, no se asumió:

```bash
az rest --method get --url \
  "https://management.azure.com/subscriptions/<sub-id>/providers/Microsoft.Web/locations/eastus2/usages?api-version=2023-12-01"
```

**Resultado:** la suscripción de prueba tiene cuota `0` para planes Linux
en `eastus2` — un bloqueo duro, no una limitación de tamaño de plan (F1
tampoco funcionaba).

Se probó de forma empírica la disponibilidad de cuota B1 Linux en un lote
de regiones candidatas:

```bash
for reg in westus2 westeurope northeurope centralus canadacentral brazilsouth uksouth; do
  az group create -n "rg-quota-$reg" -l "$reg"
  az appservice plan create -g "rg-quota-$reg" -n "plan-test-b1-$reg" --sku B1 --is-linux
done
```

`westeurope` fue la región donde el plan B1 Linux se creó sin error de
cuota, con soporte confirmado de integración regional con VNet. Los grupos
de recursos de prueba se eliminaron al terminar (`az group delete ...
--no-wait`) para no dejar cargos residuales.

## 3. Disponibilidad de servicios de semanas 2 y 3 (verificada)

Según `docs/informe-cuotas.md` §2, evaluado sobre `westeurope`:

| Servicio | Disponible en West Europe | Estado |
|---|---|---|
| Azure AI Document Intelligence (FormRecognizer) | ✅ Sí, incluye nivel gratuito F0 | Verificado |
| Azure Cognitive Services (multi-servicio) | ✅ Sí | Verificado |
| Azure Cosmos DB / SQL (almacén relacional/documental, semana 2) | ⚠️ No evaluado todavía | **Pendiente** |

**Riesgo abierto:** el informe de cuotas (`docs/informe-cuotas.md` §5)
deja explícitamente pendiente la verificación de Cosmos DB/SQL en esta
región. La sección 2.1 de `Azure-Semana1.md` exige que el informe de
cuotas condicione el diseño *antes* de comprometer decisiones de
arquitectura — este punto debe cerrarse antes de iniciar la semana 2,
no se da por resuelto aquí.

## 4. Costo

Una vez `eastus2` quedó descartado por el bloqueo de cuota (criterio
eliminatorio, no de costo), la comparación de costo entre las regiones
candidatas dejó de ser relevante para la decisión: solo `westeurope`
confirmó cuota disponible para B1 Linux en la prueba del punto 2. Dentro
de Azure, el precio de cómputo Basic B1 en West Europe es de la misma
banda que East US 2 (ambas son regiones "Tier 1" en la lista de precios
estándar de Azure) — no hay penalización de costo significativa por el
cambio de región. El costo estimado a 21 días se documenta en
`docs/nivel-servicio-costo.md` §2.

## 5. Latencia

No se realizó una medición empírica de latencia (no hay un requisito de
SLA de usuarios finales en la semana 1: el sistema opera con tráfico de
prueba de la propia célula, no con usuarios reales). Se prioriza
disponibilidad de cuota — un bloqueo duro y verificado — sobre una
optimización de latencia no cuantificada. Si en semanas posteriores se
define una ubicación geográfica real de los usuarios/comercios que
Centinela debe servir, este criterio debe reevaluarse explícitamente;
por ahora no hay información para hacerlo.

## 6. Decisión

**West Europe (`westeurope`, `regionShort=weu`)**, por ser la única
región verificada con cuota activa para App Service Linux B1 con
integración a VNet, con Document Intelligence disponible para la semana
2/3. Pendiente antes de comprometer el diseño de semana 2: verificar
cuota de Cosmos DB/SQL en esta misma región (ver §3).