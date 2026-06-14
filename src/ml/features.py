"""Construcción de variables (features) para el modelo de tránsitos.

Decisiones (ver README / discusión de gates):
- `lluvia_acum_12m`: lluvia acumulada de 12 meses. Se elige por MECANISMO
  (balance hídrico anual del Canal: el déficit se integra en el Lago Gatún
  durante ~1 año antes de afectar la capacidad), no por maximizar correlación.
- SIN rezago en la lluvia: un rezago ajustado salía de un único episodio de
  sequía (n=1) -> sería sobreajuste indefendible.
- SIN `anio` (un RandomForest no extrapola años nuevos) y SIN `nivel_lago_m`
  (correlaciona con los tránsitos por construcción del respaldo).
- La tendencia la cargan los rezagos de la propia serie (`lag1`, `lag12`).
"""
from __future__ import annotations

import pandas as pd

FEATURES = ["mes", "lluvia_mm", "lluvia_acum_12m", "transitos_lag1", "transitos_lag12"]
TARGET = "transitos_total"


def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    """Genera las features y el target a partir del dataset mensual.

    Devuelve un DataFrame con [fecha] + FEATURES + [TARGET], sin filas con NaN
    (se descartan los primeros 12 meses consumidos por los rezagos/acumulado).
    """
    df = df.sort_values("fecha").reset_index(drop=True).copy()
    df["lluvia_acum_12m"] = df["lluvia_mm"].rolling(12).sum()
    df["transitos_lag1"] = df[TARGET].shift(1)
    df["transitos_lag12"] = df[TARGET].shift(12)

    cols = ["fecha"] + FEATURES + [TARGET]
    return df[cols].dropna().reset_index(drop=True)
