# Dashboards Power BI — Canal de Panamá

## 1. Cargar los datos

1. Corré, en este orden:
   ```
   python src/pipeline/export_powerbi.py       # -> DimFecha, DimEsclusa, FactTransitos, FactClima, FactPronostico
   python src/ingesta/scraper_tarifas.py        # -> data/raw/tarifas.csv
   python src/pricing/calculo_ingresos.py       # -> FactIngresos.csv (peaje + CAD + prima de subasta FY2024)
   ```
   Los tres escriben en `data/powerbi/`. El orden importa: `export_powerbi.py`
   crea `DimFecha`/`DimEsclusa` primero; `calculo_ingresos.py` reutiliza esos
   mismos `fecha_id`/`esclusa_id` para que `FactIngresos` calce con el resto.
2. En Power BI Desktop: **Obtener datos → Carpeta** → apuntá a `data/powerbi/`
   → **Combinar y transformar** los 6 CSV (o cargalos uno por uno con
   **Obtener datos → Texto/CSV**).
3. En **Modelo**, creá las relaciones (todas 1 → * desde las dimensiones):
   - `DimFecha[fecha_id]` → `FactTransitos[fecha_id]`
   - `DimFecha[fecha_id]` → `FactClima[fecha_id]`
   - `DimFecha[fecha_id]` → `FactPronostico[fecha_id]`
   - `DimFecha[fecha_id]` → `FactIngresos[fecha_id]`
   - `DimEsclusa[esclusa_id]` → `FactTransitos[esclusa_id]`
   - `DimEsclusa[esclusa_id]` → `FactIngresos[esclusa_id]`
4. Marcá `DimFecha` como **tabla de fechas** (Modelado → Marcar como tabla de
   fechas, columna `fecha`).

## 2. Medidas DAX (pegar en una tabla nueva "Medidas")

```dax
Total Tránsitos = SUM(FactTransitos[transitos])

Tránsitos Año Anterior =
CALCULATE([Total Tránsitos], SAMEPERIODLASTYEAR(DimFecha[fecha]))

Variación Interanual % =
DIVIDE([Total Tránsitos] - [Tránsitos Año Anterior], [Tránsitos Año Anterior])

Tonelaje Total (M) = DIVIDE(SUM(FactTransitos[tonelaje]), 1000000)

Lluvia Acumulada 12m =
CALCULATE(MAX(FactClima[lluvia_acum_12m]))

Nivel Lago Promedio = AVERAGE(FactClima[nivel_lago_m])

Correlación Lluvia-Tránsitos =
VAR t = SUMMARIZE(FactClima, DimFecha[fecha_id], "x", [Lluvia Acumulada 12m], "y", [Total Tránsitos])
RETURN
  DIVIDE(
    SUMX(t, ([x]-AVERAGEX(t,[x]))*([y]-AVERAGEX(t,[y]))),
    SQRT(SUMX(t,([x]-AVERAGEX(t,[x]))^2) * SUMX(t,([y]-AVERAGEX(t,[y]))^2))
  )

% Panamax =
DIVIDE(
  CALCULATE([Total Tránsitos], DimEsclusa[esclusa_nombre]="Panamax"),
  [Total Tránsitos]
)

% Neopanamax = 1 - [% Panamax]

Pronóstico Próx 3 Meses =
CALCULATE(AVERAGE(FactPronostico[pred]),
  DATESBETWEEN(DimFecha[fecha], TODAY(), EDATE(TODAY(),3)))

MAE Modelo = 10.7          -- valor fijo desde models/metricas.json
RMSE Modelo = 12.5         -- ídem

Ingreso Total (Peaje+CAD) = SUM(FactIngresos[ingreso_mensual_usd])

Ingreso Total con Subasta = SUM(FactIngresos[ingreso_mensual_con_subasta_usd])

Prima de Subasta = SUM(FactIngresos[prima_subasta_usd])

Ingreso Promedio por Tránsito = DIVIDE([Ingreso Total con Subasta], [Total Tránsitos])
```

> Los últimos dos (`MAE Modelo`, `RMSE Modelo`) también se pueden traer como
> tabla desde `models/metricas.json` en vez de fijarlos; se dejan como
> constantes aquí para simplicidad si no querés cargar ese JSON como tabla.

## 3. Páginas del reporte (equivalentes a las del Streamlit + mejoras)

### Página 1 — Resumen ejecutivo
- 6 tarjetas (KPI cards): `Total Tránsitos`, `Variación Interanual %`,
  `Tonelaje Total (M)`, `Nivel Lago Promedio`, `Pronóstico Próx 3 Meses`,
  `Correlación Lluvia-Tránsitos`.
- Slicer de rango de fechas (`DimFecha[fecha]`) y de tipo de esclusa
  (`DimEsclusa[esclusa_nombre]`).
- Gráfico de líneas: `Total Tránsitos` por `DimFecha[etiqueta]`.

### Página 2 — Tendencias
- Gráfico de líneas: tránsitos mensuales, separado por `esclusa_nombre`
  (leyenda).
- Gráfico de barras: `Tonelaje Total (M)` por año fiscal.
- Gráfico combinado (líneas + barras): tránsitos vs. tonelaje.

### Página 3 — Agua vs. Tránsitos
- Gráfico de dispersión: `Lluvia Acumulada 12m` (eje X) vs. `Total Tránsitos`
  (eje Y), con línea de tendencia activada.
- Tarjeta con `Correlación Lluvia-Tránsitos`.
- Gráfico de líneas dual-eje: lluvia mensual vs. tránsitos mensuales.

### Página 4 — Composición por esclusa
- Gráfico de anillo (donut): `% Panamax` / `% Neopanamax`.
- Gráfico de barras apiladas: tránsitos por esclusa a lo largo del tiempo.

### Página 5 — Pronóstico y calidad del modelo
- Gráfico de líneas con banda: `FactPronostico[pred]`, `lo`, `hi` (usar un
  gráfico de área para la banda + línea para `pred`).
- Tarjetas: `MAE Modelo`, `RMSE Modelo`.
- Tabla: comparación pronóstico vs. real (donde haya datos reales que se
  solapen con el pronóstico).

### Página 6 — Ingresos (peaje, CAD y subastas)
- 3 tarjetas: `Ingreso Total con Subasta`, `Prima de Subasta`, `Ingreso
  Promedio por Tránsito`.
- Gráfico de líneas: `Ingreso Total (Peaje+CAD)` vs. `Ingreso Total con
  Subasta` por `DimFecha[etiqueta]` — la brecha entre ambas líneas en
  oct-2023 a sep-2024 (FY2024) es la prima de subasta.
- Gráfico combinado: `Total Tránsitos` (barras) vs. `Ingreso Total con
  Subasta` (línea, eje secundario), filtrado a FY2024. Este es el gráfico que
  responde directamente a "por qué los ingresos no cayeron con la sequía"
  (ver `docs/METODOLOGIA_PRECIOS.md` §6).
- Nota de texto en la página: aclarar que el peaje base es una ancla pública
  estimada y que la prima de subasta reparte un total real ($450M FY2024) de
  forma proporcional por mes (no es un dato oficial mensual).

## 4. Formato condicional sugerido

- En la tabla de composición por esclusa: escala de color en `Total Tránsitos`
  (rojo→verde) para resaltar meses bajos por la sequía 2023–2024.
- En `Variación Interanual %`: iconos (▲/▼) con reglas `SWITCH(TRUE(), ...)`
  igual que hiciste en el dashboard de ventas (verde si > 0, rojo si < 0).

## 5. Publicación

`Archivo → Publicar → Power BI Service` (requiere cuenta de Power BI/Office
365 institucional o gratuita). Si el examen pide solo el `.pbix`, no hace
falta publicarlo, con guardarlo alcanza.
