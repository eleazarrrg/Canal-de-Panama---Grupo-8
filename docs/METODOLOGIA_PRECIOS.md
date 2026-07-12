# Metodología — Precio real (peaje) e ingresos estimados

## 1. Qué es real y qué es estimado (léase antes de usar las cifras)

Siguiendo la misma honestidad metodológica que ya tiene el proyecto para
tránsitos (ver README §6-7), el ingreso mensual se separa en dos partes:

| Componente | Estado | Fuente |
|---|---|---|
| **Mecanismo del CAD** (fijo $10,000 + variable 1%-10% según nivel del lago) | **Real** | Comunicados oficiales de la ACP (cargo por agua dulce, vigente desde feb-2020) |
| **Peaje base por tránsito** (Panamax ≈ $90,000, Neopanamax ≈ $350,000) | **Estimado** (ancla pública) | Órdenes de magnitud reportados en prensa/industria; el tarifario oficial de la ACP tiene ~60 renglones que varían por tonelaje, tipo de carga y condición de lastre — no hay un "precio único" público por tránsito |
| **Nivel del lago → % variable del CAD** | Interpolación lineal documentada | Ancla: ~79 pies (sequía severa) → 10%; ~92 pies (nivel óptimo) → 1%. La ACP no publica la curva exacta de interpolación, así que se aproxima linealmente entre los dos extremos documentados. |

**Conclusión:** el *ingreso_mensual_usd* es una **estimación de orden de
magnitud**, útil para ver la tendencia y el efecto de la sequía sobre los
ingresos (que es el objetivo del análisis), no una cifra contable exacta.
Esto es equivalente, en espíritu, a cómo el proyecto ya trata el detalle
mensual de tránsitos: reales en el mecanismo y el ancla, estimados en el
detalle fino.

## 2. Por qué no se scrapeó un histórico oficial de ingresos

La ACP publica:
- El tarifario vigente (foto del presente, no histórico).
- Reportes financieros anuales (ingresos totales, no desagregados por
  tránsito ni por mes).

No existe un dataset público con "ingreso por tránsito individual" — sería
información comercial sensible de cada naviera. Por eso el enfoque correcto
(y el mismo que ya usa el proyecto para tránsitos) es aplicar el **mecanismo
real de precios** sobre los **volúmenes reales/estimados de tránsitos**, en
vez de inventar una serie de ingresos desde cero.

## 3. Cómo correr el pipeline de precios

```
python src/ingesta/scraper_tarifas.py     # -> data/raw/tarifas.csv
python src/pricing/calculo_ingresos.py    # -> data/processed/ingresos.csv
                                            #    data/powerbi/FactIngresos.csv
```

`scraper_tarifas.py` intenta verificar que el tarifario público siga
accesible (no parsea el PDF completo, cuya estructura de ~60 renglones es
inestable); si no hay red o el sitio bloquea el acceso, usa las anclas
documentadas igual, marcando la fuente como `ancla_publica_sin_verificar`.

## 4. Integración con el modelo estrella

`FactIngresos.csv` se relaciona con `DimFecha` (por `fecha_id`) y
`DimEsclusa` (por `esclusa_id`), igual que `FactTransitos`. Agregalo en
Power BI con **Obtener datos → Carpeta** junto a los demás CSV de
`data/powerbi/`; las relaciones se crean automáticamente si los nombres de
columna coinciden, o manualmente si no.

## 6. El caso FY2024: por qué los ingresos NO cayeron con la sequía (dato real)

Esto responde a la pregunta que probablemente te haga el profesor: en el año
fiscal 2024 (oct-2023 a sep-2024) los tránsitos cayeron **9.2%** y el tonelaje
**13.1%** por la sequía, pero los ingresos operativos de la ACP **subieron 1%**
(a B/.4,986 millones) — en vez de caer los ~$800-850M que la propia ACP había
proyectado en enero de 2024.

La diferencia se explica principalmente por un **"ingreso excepcional de
aproximadamente $450 millones"** de las **subastas de turnos preferenciales de
cruce**: cuando escasearon los cupos diarios, algunas navieras pagaron sumas
grandes para saltarse la fila de espera (que llegó a 163 buques, la más larga
de la historia del Canal) en vez de esperar semanas. A esto se suma el Cargo
por Agua Dulce y los ajustes de tarifa ya programados desde 2022.

**Fuente:** declaraciones del vicepresidente de finanzas de la ACP en la
presentación de resultados financieros FY2024 (25-oct-2024); cobertura de
Infobae y Panamá América el mismo día.

### Cómo se modela esto en `calculo_ingresos.py`

La ACP no publica el desglose mensual de esos $450M (es un total anual). El
script:
1. Toma el **total real** ($450,000,000).
2. Calcula, para cada mes de FY2024, un "déficit de tránsitos" = tránsitos
   normales esperados (promedio histórico del mismo mes calendario, excluyendo
   FY2024) − tránsitos reales de ese mes.
3. Reparte el total real entre los meses proporcional a ese déficit: los meses
   con más escasez de cupos (nov-2023 a mar-2024, el peor tramo de la sequía)
   reciben una porción mayor de la prima de subasta.

Esto produce `prima_subasta_usd` e `ingreso_mensual_con_subasta_usd` en
`ingresos.csv`. **El total anual es real y verificable; la distribución
mensual es una estimación razonable, no un dato oficial mes a mes** — se
documenta así explícitamente, siguiendo la misma honestidad metodológica del
resto del proyecto.

### Qué mostrar en el dashboard

Comparar `ingreso_mensual_usd` (sin subasta) vs. `ingreso_mensual_con_subasta_usd`
en el mismo gráfico durante FY2024 hace visible el efecto: la línea "con
subasta" se mantiene casi plana pese a la caída de tránsitos, mientras que la
línea sin subasta sí muestra la caída que uno esperaría solo por menos buques.

## 7. Próximo paso opcional (si el profesor pide precisión real)

Si se consigue acceso a un reporte financiero anual desglosado de la ACP
(ingresos totales por año fiscal), se puede **calibrar** el peaje base ancla
para que el ingreso anual estimado coincida con el ingreso anual real
reportado, y así las cifras estimadas quedan ancladas a un total verificado
(mismo patrón que ya usa `fallback.py` con los totales anuales reales de
tránsitos).
