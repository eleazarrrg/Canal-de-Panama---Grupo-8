# Justificación del modelo de Machine Learning

## 1. Tipo de problema

Se trata de un problema de **regresión**: predecir `transitos_total` (número de
buques que cruzan el Canal por mes), una variable numérica continua, a partir de
variables explicativas (clima acumulado, mes, historial reciente).

No es clasificación (no hay categorías discretas que predecir) ni clustering (no
buscamos agrupar observaciones sin etiqueta; ya tenemos el target real: los
tránsitos mensuales).

## 2. Modelo elegido: `RandomForestRegressor`

### Por qué Random Forest y no otras alternativas

| Alternativa considerada | Por qué se descartó |
|---|---|
| Regresión lineal | La relación agua→cupos→tránsitos no es lineal (los cupos cambian por escalones administrativos, no de forma continua con la lluvia). Un modelo lineal no captura ese efecto de "umbral". |
| ARIMA / SARIMA | Sirve para pronosticar solo con la propia serie histórica, pero no incorpora fácilmente variables exógenas como la lluvia acumulada, que es la relación central que el proyecto quiere demostrar. |
| Redes neuronales (LSTM, etc.) | Con 132 observaciones mensuales, una red profunda sobreajusta casi con certeza; no hay datos suficientes para justificar su complejidad. |
| Random Forest Regressor | Maneja relaciones no lineales y efectos de umbral sin necesidad de especificarlos a mano, es robusto a outliers, no requiere escalado de variables, y con pocos datos generaliza mejor que modelos de alta varianza (redes neuronales) gracias al *bagging* (promedio de muchos árboles entrenados con submuestras). |

En resumen: Random Forest es el punto óptimo entre **capacidad de capturar
no linealidad** (necesaria, porque los cupos de tránsito cambian por decisión
administrativa, no de forma suave) y **robustez con pocos datos** (132 meses).

## 3. Variables (features) y por qué

- `mes`: captura estacionalidad del comercio marítimo.
- `lluvia_mm`: lluvia del mes corriente (señal débil, se incluye como contraste).
- `lluvia_acum_12m`: lluvia acumulada de los últimos 12 meses. **Es la variable
  clave**, elegida por mecanismo físico (el balance hídrico del Lago Gatún es
  anual, no mensual), no por ser la que más correlaciona.
- `transitos_lag1`: tránsitos del mes anterior (inercia operativa: el Canal no
  cambia su ritmo de un mes a otro de forma abrupta salvo por un evento de
  cupos).
- `transitos_lag12`: tránsitos del mismo mes el año anterior (estacionalidad
  anual).

**Variables excluidas deliberadamente:**
- `anio`: un Random Forest no puede extrapolar fuera del rango de años vistos en
  entrenamiento (a diferencia de una regresión lineal, que sí extrapola, aunque
  mal). Incluirlo generaría pronósticos planos o erráticos fuera de rango.
- `nivel_lago_m`: en los datos de respaldo, el nivel del lago se construye a
  partir del mismo calendario administrativo que determina los cupos de
  tránsito. Usarlo como feature sería **circular** (el modelo "adivinaría" el
  target a partir de una variable que ya lo contiene indirectamente).

## 4. Evaluación y resultados

- **Validación:** split temporal (no aleatorio) — se entrena con todo el
  historial hasta antes de FY2025 y se evalúa contra los últimos 12 meses
  reales (FY2025). Esto es correcto para series de tiempo: evita que el modelo
  "vea el futuro" durante el entrenamiento, algo que un split aleatorio sí
  permitiría por accidente (data leakage temporal).
- **Métricas:**
  - MAE ≈ 10.7 tránsitos/mes
  - RMSE ≈ 12.5
  - R² ≈ 0.48 (modesto, esperado: el año de test es un período relativamente
    estable, con poca varianza que explicar)
- **Comparación contra baselines:**
  - Modelo de persistencia (repetir el último valor): MAE 13.8
  - Modelo estacional (repetir el mismo mes del año anterior): MAE 186
  - → El Random Forest mejora sustancialmente sobre ambos baselines ingenuos,
    que es el criterio correcto para juzgar si un modelo "vale la pena" en
    series de tiempo cortas.
- **Importancia de variables:** `transitos_lag1` (0.70) domina, seguido de
  `lluvia_acum_12m` (0.20). Esto es coherente con la tesis del proyecto: el
  agua acumulada explica una porción real pero secundaria de la varianza; la
  inercia operativa mes a mes explica la mayoría.

## 5. Limitaciones honestas

- Con 132 observaciones mensuales y un solo episodio de sequía en la muestra
  (n=1 a nivel de "evento"), no se puede afirmar *skill* predictivo general;
  el modelo describe bien la relación agua↔capacidad observada, pero no está
  probado en un segundo ciclo de sequía independiente.
- R²=0.48 no es alto en términos absolutos, pero es el esperable dado que el
  período de test es casi plano (poca varianza que un modelo, cualquiera que
  sea, pueda "explicar" en términos relativos).
