"""Respaldo: construye la serie MENSUAL de tránsitos a partir de controles
ANUALES reales. NO incrusta la relación agua -> tránsitos.

Método (documentado en el README):
1. Control anual real por año fiscal (verificado FY2024/FY2025; anclaje
   público aproximado para años previos).
2. Reparto a meses con estacionalidad suave + el CALENDARIO REAL DE CUPOS
   diarios de la ACP, que es independiente de la lluvia. La caída de la
   sequía sale de este calendario (evento real por fecha), no de una fórmula
   sobre la precipitación.
3. Calibración para que la suma mensual sea exactamente el control anual.

El detalle mensual se etiqueta fuente='estimado'. El dato real es el total
anual; el reparto mensual es una estimación.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

RAW = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "transitos_estimado.csv"

# --- 1) Controles anuales (tránsitos oceaneros totales = panamax + neopanamax)
# Verificados: FY2024, FY2025. Resto: anclaje público aproximado (refinable
# con el scraper). transitos_total = total oficial ACP por tipo de esclusa.
CONTROLES_ANUALES = {
    2015: 13900, 2016: 13100, 2017: 13500, 2018: 13800, 2019: 13800,
    2020: 13400, 2021: 13300, 2022: 14200, 2023: 14080,
    2024: 11240,            # verificado
    2025: 13404,            # verificado (10.062 panamax + 3.342 neopanamax)
}
FY_VERIFICADOS = {2024, 2025}

# Participación de neopanamax por año fiscal (esclusas nuevas abrieron jun-2016).
NEO_SHARE_FY = {
    2015: 0.00, 2016: 0.05, 2017: 0.17, 2018: 0.20, 2019: 0.21,
    2020: 0.22, 2021: 0.23, 2022: 0.24, 2023: 0.25,
    2024: 0.24, 2025: 3342 / 13404,
}
NEO_INICIO = pd.Timestamp("2016-07-01")  # primer mes con tránsitos neopanamax

# Estacionalidad mensual suave (1=ene .. 12=dic), media ~1.0. Amplitud pequeña
# porque no hay forma real de conocer la forma intra-anual; el dato fuerte es
# el control anual + el calendario de cupos.
ESTACIONALIDAD = {
    1: 1.02, 2: 1.01, 3: 1.03, 4: 1.02, 5: 1.00, 6: 0.98,
    7: 0.98, 8: 0.99, 9: 0.99, 10: 1.00, 11: 0.99, 12: 0.99,
}

# Tonelaje CP/SUAB (no toneladas largas): anclado a FY2025 (489.1 M).
# Un neopanamax pesa ~2.5x un panamax (esclusas nuevas, buques mayores):
#   10.062*tpp + 3.342*2.5*tpp = 489.1e6  ->  tpp ≈ 26.557
TPP_PANAMAX = 26_557.0
TPP_NEOPANAMAX = TPP_PANAMAX * 2.5

# --- Calendario REAL de cupos diarios de la ACP (independiente de la lluvia) ---
# Hitos documentados de las restricciones por la sequía 2023–2024:
# ~36 normal -> 32 -> 31 -> 25 (nov-2023) -> 24 -> recuperación a 36 (sep-2024).
CUPOS = [
    ("2000-01-01", 36),   # normal histórico
    ("2023-08-08", 32),
    ("2023-09-15", 31),
    ("2023-11-03", 25),
    ("2023-12-01", 24),   # mínimo sostenido (las lluvias evitaron bajar más)
    ("2024-03-18", 27),
    ("2024-04-15", 31),
    ("2024-05-16", 32),
    ("2024-07-01", 34),
    ("2024-08-05", 35),
    ("2024-09-03", 36),   # normalización
]
_CUPOS = [(pd.Timestamp(f), v) for f, v in CUPOS]

# Nivel del Lago Gatún (m) — SOLO contexto del dashboard, NO es feature de ML
# (sale del mismo calendario que los cupos -> correlación por construcción).
NIVEL_LAGO = [
    ("2014-10-01", 26.7), ("2023-04-01", 26.6), ("2023-07-01", 24.9),
    ("2023-09-01", 24.3), ("2024-01-01", 24.2), ("2024-04-15", 24.1),
    ("2024-06-15", 25.0), ("2024-08-15", 26.0), ("2024-10-01", 26.6),
    ("2025-09-30", 26.7),
]


def dataset_respaldo() -> pd.DataFrame:
    """Serie mensual estimada de tránsitos (oct-2014 .. sep-2025)."""
    return construir_serie_mensual(CONTROLES_ANUALES)


def construir_serie_mensual(controles: dict) -> pd.DataFrame:
    """Reparte cada control anual en meses (estacionalidad x calendario de cupos)."""
    meses = pd.date_range("2014-10-01", "2025-09-01", freq="MS")
    df = pd.DataFrame({"fecha": meses})
    df["anio"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month
    df["anio_fiscal"] = df["fecha"].apply(_anio_fiscal)
    df["peso"] = _factor_capacidad(meses) * df["mes"].map(ESTACIONALIDAD)

    # Reparto por año fiscal: total mensual proporcional al peso, suma = control.
    df["transitos_total"] = 0
    for fy in df["anio_fiscal"].unique():
        if fy not in controles:
            continue
        m = df["anio_fiscal"] == fy
        bruto = controles[fy] * df.loc[m, "peso"] / df.loc[m, "peso"].sum()
        df.loc[m, "transitos_total"] = _redondear_a_total(bruto, controles[fy])

    # Split panamax / neopanamax (neopanamax = 0 antes de jun-2016).
    share = df["anio_fiscal"].map(NEO_SHARE_FY).fillna(0.0)
    neo = (df["transitos_total"] * share).round().astype(int)
    neo[df["fecha"] < NEO_INICIO] = 0
    df["transitos_neopanamax"] = neo
    df["transitos_panamax"] = df["transitos_total"] - df["transitos_neopanamax"]

    # Tonelaje CP/SUAB (estimado, anclado a FY2025; neopanamax pesa más).
    df["tonelaje"] = (
        df["transitos_panamax"] * TPP_PANAMAX
        + df["transitos_neopanamax"] * TPP_NEOPANAMAX
    ).round().astype("int64")

    # Nivel del lago (contexto).
    df["nivel_lago_m"] = _nivel_lago(meses).round(2)

    df["fuente"] = "estimado"
    cols = [
        "fecha", "anio", "mes", "anio_fiscal", "transitos_total",
        "transitos_panamax", "transitos_neopanamax", "tonelaje",
        "nivel_lago_m", "fuente",
    ]
    out = df[cols].copy()
    RAW.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(RAW, index=False)
    return out


def _anio_fiscal(fecha: pd.Timestamp) -> int:
    """Año fiscal ACP (oct–sep). Oct-2024..Sep-2025 -> FY2025."""
    return fecha.year + 1 if fecha.month >= 10 else fecha.year


def _cupo_diario(fechas: pd.DatetimeIndex) -> np.ndarray:
    """Cupo diario vigente en cada fecha (función escalón)."""
    cap = np.full(len(fechas), _CUPOS[0][1], dtype=float)
    for f, v in _CUPOS:
        cap[fechas >= f] = v
    return cap


def _factor_capacidad(meses: pd.DatetimeIndex) -> np.ndarray:
    """Factor de capacidad mensual = cupo medio del mes / 36 (cupo normal)."""
    out = []
    for m in meses:
        dias = pd.date_range(m, m + pd.offsets.MonthEnd(0), freq="D")
        out.append(_cupo_diario(dias).mean() / 36.0)
    return np.array(out)


def _nivel_lago(meses: pd.DatetimeIndex) -> np.ndarray:
    """Interpola el nivel del lago (contexto) en cada mes."""
    fechas = pd.to_datetime([f for f, _ in NIVEL_LAGO]).astype("int64")
    vals = np.array([v for _, v in NIVEL_LAGO])
    return np.interp(meses.astype("int64"), fechas, vals)


def _redondear_a_total(bruto: pd.Series, total: int) -> pd.Series:
    """Redondea a enteros forzando que la suma sea exactamente 'total'."""
    base = np.floor(bruto).astype(int)
    resto = int(total - base.sum())
    orden = (bruto - base).sort_values(ascending=False).index
    base.loc[orden[:resto]] += 1
    return base


if __name__ == "__main__":
    out = dataset_respaldo()
    print(out.head(15).to_string())
    print("...")
    print(out.tail(15).to_string())
