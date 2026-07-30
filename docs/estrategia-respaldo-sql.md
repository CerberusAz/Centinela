# Estrategia de respaldo — Almacén de casos (Azure SQL)

Entregable 4 de semana 2. Azure-Semana2.md, sección 2.2: "estrategia de
respaldo documentada: periodicidad, retención y pérdida máxima tolerable
de datos."

## 1. Mecanismo: backups automáticos gestionados por la plataforma

Azure SQL Database (Serverless General Purpose, `infra/bicep/modules/sql.bicep`)
incluye backups automáticos gestionados por Azure, sin configuración
adicional ni script propio — a diferencia del almacén de objetos de
semana 1, donde la política de ciclo de vida sí se definió explícitamente
(`storage.bicep`), aquí no hay una decisión de diseño que tomar sobre el
mecanismo en sí: viene incluido en el nivel de servicio.

**Composición del backup automático (General Purpose):**

- **Backups completos:** semanales.
- **Backups diferenciales:** cada 12-24 horas.
- **Backups de log de transacciones:** cada 5-10 minutos.

Estos tres niveles combinados permiten una restauración point-in-time
(PITR) a cualquier instante dentro de la ventana de retención, no solo a
los puntos de backup completo/diferencial.

## 2. Periodicidad y retención

| Parámetro | Valor | Fuente |
|---|---|---|
| Retención de backups (PITR) | 7 días | Valor por defecto del nivel General Purpose — no se modificó en `sql.bicep` |
| Frecuencia de log backup | 5-10 minutos | Gestionado por la plataforma, no configurable |
| Long-Term Retention (LTR) | No configurada esta semana | Fuera de alcance — se evaluaría en semana 3 si el volumen de casos justifica retención más allá de 7 días |

**Por qué 7 días es suficiente para esta semana:** el almacén de casos
tiene "volumen bajo" (sección 2.2) — la célula está en fase de prueba de
21 días, sin datos de producción real que ameriten una política de
retención regulatoria todavía. Si se requiere retención más larga (p.
ej. por normativa financiera real), Azure SQL soporta LTR configurable
hasta 10 años — evaluar cuando exista ese requisito concreto, no antes.

## 3. Pérdida máxima tolerable de datos (RPO)

**RPO estimado: 5-10 minutos**, determinado por la frecuencia de los
backups de log de transacciones (el componente que acota cuánto se puede
perder entre el último log backup y un fallo).

**Por qué es aceptable para este componente:** el almacén de casos recibe
escrituras de bajo volumen (un caso por transacción que supera el
umbral, no por cada transacción) — la probabilidad de que un fallo
coincida exactamente con la ventana de 5-10 minutos sin backup es baja, y
el impacto de perder un caso reciente (recreable si la transacción y el
score original siguen en Cosmos DB, con TTL de 30 días — ver
`docs/justificacion-particionamiento-cosmos.md`) es menor que el de
perder datos financieros primarios. La transacción cruda en sí (Blob
Storage, semana 1) no depende de este RPO en absoluto.

## 4. Restauración — comando de referencia

```bash
az sql db restore \
  --resource-group <rg> \
  --server <sql-server-name> \
  --name centinela-casos \
  --dest-name centinela-casos-restaurada \
  --time "2026-08-15T10:00:00Z"
```

Restaura a una base nueva (no sobrescribe la original) — el paso
siguiente de promoción/rename es manual y depende del escenario de
incidente real. No ejecutado en este entorno de desarrollo (requiere una
base ya desplegada con historial de backups).

## 5. Riesgo documentado

Este documento describe el comportamiento *documentado* de Azure SQL
General Purpose Serverless con Free Offer. No se verificó contra una
instancia real desplegada en este entorno (sin `az`/red hacia Azure) —
antes de dar por cerrado este entregable, confirmar contra la instancia
real con:

```bash
az sql db show \
  --resource-group <rg> --server <sql-server-name> --name centinela-casos \
  --query "{retencionBackup: earliestRestoreDate}"
```
