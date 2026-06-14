# Documentación para aprender — Análisis de Datos del Canal de Panamá

Grupo 8 · UTP, FISC · I Semestre 2026

Este documento explica **todo lo que se hizo**, en lenguaje claro, para que cada
integrante entienda el proyecto completo y pueda explicar su parte. El README es la
guía técnica de instalación/despliegue; este archivo es la **guía de estudio**.

---

## 1. ¿De qué trata el proyecto? (la idea en una página)

El Canal de Panamá funciona con **agua dulce**: cada vez que un barco cruza, las
esclusas vacían millones de litros del **Lago Gatún** hacia el mar. Ese lago se
llena con **lluvia**. Conclusión: si llueve poco, el lago baja, y la autoridad del
Canal (ACP) tiene que **reducir cuántos barcos deja pasar por día** (los "cupos").

Eso pasó de verdad en la **sequía de 2023–2024**: los cupos bajaron de ~36 a ~24
barcos por día y el volumen de tránsitos cayó cerca de **30 %**. Luego, con las
lluvias de 2024, se recuperó.

La **tesis** del proyecto es esa cadena:

> **lluvia (agua) → nivel del lago → capacidad (cupos) → tránsitos (barcos)**

El proyecto:
1. Junta datos de **dos fuentes** (clima real + estadísticas del Canal).
2. Los limpia y arma una tabla mensual.
3. Entrena un **modelo de Machine Learning** que predice los tránsitos.
4. Muestra todo en un **dashboard interactivo** (web) con gráficas, mapa y un
   **resumen escrito por inteligencia artificial**.

---

## 2. ¿Qué tecnologías se usaron y para qué?

| Herramienta | Para qué sirve aquí |
|---|---|
| **Python** | Lenguaje de todo el proyecto |
| **pandas** | Manejar tablas de datos (filas y columnas) |
| **requests** | Pedir datos a una API por internet (el clima) |
| **BeautifulSoup** | "Raspar" (leer) datos de páginas web (el scraper) |
| **scikit-learn** | El modelo de Machine Learning (Random Forest) |
| **Streamlit** | Convertir el código en una página web interactiva (el dashboard) |
| **Plotly** | Gráficas interactivas |
| **Folium** | El mapa del Canal |
| **google-genai (Gemini)** | La IA que escribe el resumen ejecutivo |

---

## 3. Las dos fuentes de datos

**Fuente 1 — Clima (real).** Se baja de **Open-Meteo**, una API gratis y sin clave.
Se piden la lluvia y la temperatura diarias de la zona del Lago Gatún
(coordenadas 9.18, −79.92), desde 2014 hasta 2026. Estos datos son **100 % reales**.

**Fuente 2 — Tránsitos del Canal.** Se intenta "raspar" de las páginas públicas de
la ACP / Portal Logístico de Panamá. De ahí salen los **totales por año** de
tránsitos.

> **Un punto honesto e importante:** el Canal no publica de forma confiable cuántos
> barcos pasaron **cada mes**. Por eso, el detalle mensual se **estima** a partir de
> los totales anuales reales (ver sección 4). Cada fila de la tabla lleva una
> columna `fuente` que dice si es `real` o `estimado`, para no confundir.

---

## 4. ¿Cómo se arman los datos de tránsitos? (lo más importante de entender)

No inventamos números al azar. El método tiene una lógica que hay que poder
defender:

1. **Tomamos los totales anuales reales** del Canal. Por ejemplo:
   - Año fiscal 2024 = 11.240 tránsitos.
   - Año fiscal 2025 = 13.404 tránsitos (10.062 panamax + 3.342 neopanamax).
   *(El "año fiscal" del Canal va de octubre a septiembre.)*
2. **Repartimos** ese total entre los 12 meses usando dos cosas:
   - una **estacionalidad suave** (algunos meses un poco más que otros), y
   - el **calendario real de cupos** de la ACP (cuántos barcos por día se permitían
     en cada fecha: 36 normal → 25 en noviembre 2023 → 24 → recuperación a 36 en
     septiembre 2024).
3. **Ajustamos** para que la suma de los 12 meses dé exactamente el total anual real.

**¿Por qué así?** Porque queríamos que la relación "menos agua = menos tránsitos"
**apareciera sola** en los datos, no que la metiéramos a la fuerza. La caída de la
sequía la pusimos con el **calendario de cupos** (un hecho real, por fecha), **no**
calculándola desde la lluvia. Así, cuando el modelo encuentra que la lluvia y los
tránsitos se relacionan, es porque **de verdad** la lluvia real y los recortes de
cupos reales ocurrieron al mismo tiempo, no porque programamos esa fórmula.

> A esto le decimos **evitar la circularidad**: si construyéramos los tránsitos como
> una fórmula de la lluvia, el modelo solo "redescubriría" nuestra fórmula y no
> probaría nada.

---

## 5. El pipeline (los 6 pasos del flujo de datos)

```
1) fetch_clima.py    -> baja el clima real (Open-Meteo)            -> clima.csv
2) scraper_acp.py    -> intenta bajar totales del Canal            -> transitos.csv
3) fallback.py       -> arma la serie mensual (control + cupos)    -> estimado
4) build_dataset.py  -> une clima + tránsitos por mes              -> canal.parquet
5) features.py / train_model.py / forecast.py -> modelo y pronóstico
6) app.py            -> dashboard web (gráficas, mapa, IA)
```

Si el scraper falla o no hay internet, el sistema **no se cae**: usa números de
respaldo documentados y un clima de respaldo. Eso se llama **estrategia de
respaldo** y es obligatorio para que la app siempre funcione.

El resultado del pipeline es **`canal.parquet`**: una tabla de **132 meses**
(oct-2014 a sep-2025) con columnas como `fecha`, `transitos_total`,
`transitos_panamax`, `transitos_neopanamax`, `tonelaje`, `lluvia_mm`, `temp_media`,
`nivel_lago_m` y `fuente`.

---

## 6. El modelo de Machine Learning (en simple)

**Objetivo:** predecir los **tránsitos totales del mes** (`transitos_total`).

**Modelo:** **Random Forest** (un "bosque" de muchos árboles de decisión que votan;
es robusto y no necesita demasiados ajustes).

**Variables que usa (features):**
- `mes` (1–12, para la estacionalidad),
- `lluvia_mm` (lluvia del mes),
- `lluvia_acum_12m` (lluvia acumulada de los últimos 12 meses) ← **la clave**,
- `transitos_lag1` (los tránsitos del mes anterior),
- `transitos_lag12` (los tránsitos del mismo mes del año pasado).

**¿Por qué lluvia de 12 meses y no del mes?** Porque el lago acumula agua durante
~1 año. La lluvia de **un solo mes** casi no se relaciona con los tránsitos (es
ruido de estaciones), pero la lluvia **acumulada de 12 meses** sí (correlación
≈ 0.43). Lo elegimos por esa **razón física**, no por buscar el número más bonito.

**Cómo se evalúa:** se entrena con el pasado y se prueba con el **último año
(FY2025)** — esto se llama **split temporal** (no se mezclan fechas al azar, porque
sería trampa en una serie de tiempo).

**Resultados:**
- **MAE ≈ 10.7** (se equivoca en promedio ~11 tránsitos por mes, sobre ~1.100 → ~1 %).
- **RMSE ≈ 12.5**, **R² ≈ 0.48** (el R² sale modesto porque el año de prueba es casi
  plano; el MAE es lo que importa aquí).
- Le gana a predicciones ingenuas (repetir el mes anterior, o el del año pasado).
- **Importancia de variables:** el mes anterior (`lag1`) pesa 70 %, y la **lluvia
  acumulada 12m pesa 20 %** (segunda más importante) — el agua aparece sola.

---

## 7. El pronóstico (FY2026)

`forecast.py` proyecta los tránsitos de octubre 2025 a septiembre 2026:
- Usa la **lluvia real** hasta mayo 2026 y **climatología** (el promedio histórico)
  para junio–septiembre 2026.
- Es **recursivo**: predice un mes, y usa esa predicción para el siguiente.
- Dibuja una **banda de incertidumbre** (un rango, no solo una línea).

**Chequeo honesto:** comparamos el acumulado del pronóstico (9.063, base total) con
el dato real del Canal (8.593, base "alto calado"). **No son lo mismo**: la
diferencia (~470) son barcos que el conteo de "alto calado" no incluye — es
**diferencia de definición, no error del modelo**. Y que coincidan en orden es una
**corroboración de un solo período**, no una prueba de que el modelo siempre acierta.

---

## 8. El dashboard (la página web)

Hecho con **Streamlit**. Tiene una barra lateral con filtros (rango de fechas, tipo
de esclusa) y 5 páginas:

1. **Resumen** — números clave (KPIs) + un **resumen ejecutivo escrito por IA**.
2. **Tendencias** — gráficas de tránsitos y tonelaje a lo largo del tiempo.
3. **Agua vs. Tránsitos** — la gráfica estrella: muestra cómo el agua y los
   tránsitos suben y bajan juntos, con el número de correlación.
4. **Mapa** — el Canal con sus esclusas y lagos (Atlántico arriba, Pacífico abajo).
5. **Pronóstico** — la proyección de FY2026 con su banda.

---

## 9. El resumen con Inteligencia Artificial

En la página Resumen hay un texto ejecutivo de 3 párrafos. Funciona así:
- Tomamos los números ya calculados (tránsitos, variación, lluvia, pronóstico).
- Se los pasamos a **Gemini** (la IA de Google) con la instrucción de redactarlos
  en tono profesional y **sin inventar cifras**.
- **Si no hay clave de IA**, la app **no se cae**: arma el mismo texto con una
  **plantilla local**. A eso se le llama **degradación elegante**.

---

## 10. Decisiones clave y por qué (para defender el proyecto)

1. **No metimos el nivel del lago como variable del modelo.** Porque en nuestros
   datos el lago se dibuja del mismo calendario que los cupos, así que se
   relacionaría con los tránsitos "por construcción" (trampa). Lo dejamos solo como
   **contexto** en el dashboard.
2. **Usamos lluvia de 12 meses, sin retraso artificial.** Probamos que un "retraso"
   ajustado mejoraba el número, pero eso salía de **un solo evento de sequía**
   (n = 1), así que sería **forzar el dato**. Lo dejamos solo como nota exploratoria.
3. **No quitamos `lag1` para inflar la importancia de la lluvia.** Construimos el
   modelo para que **pronostique bien** y reportamos la importancia tal como salió.
   La tesis se sostiene con la correlación + la razón física, no con el ranking.
4. **Datos reales vs estimados, siempre etiquetados.** El clima es real; los totales
   anuales son reales; el detalle mensual es estimado, y se dice claramente.

---

## 11. Repartición del equipo (quién hace y aprende qué)

Cada integrante es "dueño" de una parte y debe poder explicarla. Todos apoyan en lo
demás, pero estos son los responsables principales.

| Integrante | Parte | Archivos | Conceptos a dominar |
|---|---|---|---|
| **Juan Zhu** | Ingesta de datos | `src/ingesta/` | APIs REST, web scraping, datos reales vs estimados, calendario de cupos |
| **Alex de Boutaud** | Pipeline y dataset | `src/pipeline/build_dataset.py` | Limpieza, unir tablas por fecha, agregación mensual, formato parquet |
| **Jeremy Martínez** | Machine Learning | `src/ml/` | Features, Random Forest, split temporal, MAE/RMSE/R², pronóstico |
| **Rafael Gómez** | Dashboard | `app.py` | Streamlit, gráficas Plotly, mapa Folium, KPIs, correlación |
| **Octavio Frauca** | IA + docs + despliegue | `src/llm/resumen.py`, `README.md`, deploy | LLM/Gemini, prompts, degradación, secrets, Streamlit Cloud |

### Detalle por persona

**Juan Zhu — Ingesta de datos**
- Qué hizo: bajar el clima real de Open-Meteo, intentar el scraping del Canal, y
  construir la serie mensual de respaldo con el calendario de cupos.
- Debe poder explicar: por qué el clima es real pero los tránsitos mensuales son
  estimados; cómo el calendario de cupos (no la lluvia) genera la caída de la sequía.
- Preguntas típicas: *¿De dónde salen los datos? ¿Qué pasa si la página del Canal
  cambia o no hay internet?* (respuesta: estrategia de respaldo).

**Alex de Boutaud — Pipeline y dataset**
- Qué hizo: unir clima + tránsitos en una sola tabla mensual y guardarla.
- Debe poder explicar: cómo se agregan los datos diarios de lluvia a totales
  mensuales; cómo se unen por "año-mes"; qué es la columna `fuente`.
- Preguntas típicas: *¿Por qué la tabla termina en septiembre 2025? ¿Por qué el
  clima llega hasta 2026?* (el extra es para el pronóstico).

**Jeremy Martínez — Machine Learning**
- Qué hizo: crear las variables, entrenar el Random Forest, evaluarlo y hacer el
  pronóstico con su banda.
- Debe poder explicar: qué es un split temporal y por qué no se mezcla al azar; qué
  significan MAE/RMSE/R²; por qué la lluvia de 12 meses; qué es un pronóstico
  recursivo.
- Preguntas típicas: *¿El modelo es confiable? ¿Por qué el R² no es alto?*

**Rafael Gómez — Dashboard**
- Qué hizo: la app web con sus 5 páginas, filtros, gráficas y mapa.
- Debe poder explicar: cómo Streamlit convierte Python en web; cómo los filtros
  cambian las gráficas; qué muestra la página "Agua vs. Tránsitos".
- Preguntas típicas: *¿Cómo se ve la relación agua-tránsitos? ¿Qué es la correlación
  que muestran?*

**Octavio Frauca — IA, documentación y despliegue**
- Qué hizo: el resumen con Gemini (con su plan B de plantilla), el README y subir la
  app a Streamlit Cloud.
- Debe poder explicar: cómo se le pasan los datos a la IA sin que invente cifras;
  qué es la "degradación" si no hay clave; cómo se despliega y se guardan los secretos.
- Preguntas típicas: *¿La IA inventa números? ¿Qué pasa sin la clave de IA?*

---

## 12. Glosario rápido

- **Año fiscal del Canal:** va de octubre a septiembre (FY2025 = oct-2024 a sep-2025).
- **Panamax / Neopanamax:** los dos tipos de esclusas. Las Neopanamax (más grandes)
  abrieron en 2016. `transitos_total = panamax + neopanamax`.
- **Cupos:** cantidad de barcos por día que la ACP permite reservar.
- **CP/SUAB:** el sistema de medición de tonelaje del Canal (distinto de "toneladas
  largas" de carga).
- **Feature (variable):** un dato que el modelo usa para predecir.
- **Lag (rezago):** un valor del pasado, p. ej. `lag12` = el dato de hace 12 meses.
- **Correlación (r):** número de −1 a 1 que mide si dos cosas suben/bajan juntas.
- **MAE:** error promedio (en tránsitos). **RMSE:** parecido, castiga errores grandes.
  **R²:** qué tanto explica el modelo (1 = perfecto, 0 = no explica nada).
- **Random Forest:** modelo de muchos árboles de decisión que votan.
- **Split temporal:** entrenar con el pasado y probar con el futuro (no al azar).
- **Degradación elegante:** que el sistema siga funcionando (con menos) si algo falla.

---

## 13. Cómo correr el proyecto (resumen)

Ver el **README.md** para el detalle. En corto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Los datos y el modelo ya vienen listos, así que la app abre directo. Para
regenerar todo desde cero: `build_dataset.py` → `train_model.py` → `forecast.py`.
