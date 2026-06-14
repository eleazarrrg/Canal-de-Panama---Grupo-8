"""Pipeline: une tránsitos (real con respaldo) + clima real (Open-Meteo)
y escribe data/processed/canal.parquet.

Pasos:
1. Tránsitos: intenta el scraper real -> si falla, usa anclajes documentados.
   Reparte los controles anuales a serie mensual (fuente='estimado').
2. Clima: Open-Meteo real -> agrega a mensual. Si no hay red, climatología.
3. Une por año-mes y guarda el parquet.
"""
from __future__ import annotations

import logging
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.ingesta import fallback
from src.ingesta.fetch_clima import obtener_clima
from src.ingesta.scraper_acp import ScraperACPError, obtener_transitos

log = logging.getLogger("pipeline")

INICIO = "2014-10-01"
FIN_TRANSITOS = "2025-09-30"   # fin de la serie objetivo de tránsitos (define el parquet)
# El clima se descarga MÁS ALLÁ de los tránsitos para preservar el regresor de
# lluvia del forecast (Gate 4) en data/raw/clima.csv. Al unir por la izquierda
# con los tránsitos, el parquet igual termina en sep-2025.
FIN_CLIMA = "2026-05-31"
SALIDA = ROOT / "data" / "processed" / "canal.parquet"


def construir() -> pd.DataFrame:
    """Ejecuta el pipeline completo y devuelve el dataset unido."""
    tr = _transitos()
    clima = _clima_mensual()

    tr["ym"] = tr["fecha"].dt.to_period("M")
    df = tr.merge(clima, on="ym", how="left").drop(columns="ym")

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SALIDA, index=False)
    log.info("Escrito %s (%d filas, %d columnas)", SALIDA, df.shape[0], df.shape[1])
    return df


def _transitos() -> pd.DataFrame:
    """Serie mensual de tránsitos: controles reales (scraper) + respaldo."""
    controles = dict(fallback.CONTROLES_ANUALES)
    try:
        reales = obtener_transitos()
        aceptados = 0
        for _, fila in reales.iterrows():
            fy = int(fila["anio_fiscal"])
            val = int(fila["transitos_total"])
            if fy in fallback.FY_VERIFICADOS:
                continue  # no sobrescribir los controles verificados
            ancla = fallback.CONTROLES_ANUALES.get(fy)
            # Salvaguarda: acepta el valor raspado solo si es coherente con el
            # anclaje documentado (+-15%), por si el regex laxo capturó ruido.
            if ancla is not None and abs(val - ancla) / ancla > 0.15:
                log.warning("Scrape FY%d=%d descartado (lejos del anclaje %d)", fy, val, ancla)
                continue
            controles[fy] = val
            aceptados += 1
        log.info("Scraper ACP: %d/%d totales reales aceptados", aceptados, len(reales))
    except ScraperACPError as e:
        log.warning("Scraper ACP no disponible -> anclajes documentados. %s", e)
    return fallback.construir_serie_mensual(controles)


def _clima_mensual() -> pd.DataFrame:
    """Clima mensual real (Open-Meteo) o climatología sintética si no hay red."""
    try:
        diario = obtener_clima(INICIO, FIN_CLIMA)
        fuente = "openmeteo"
    except Exception as e:  # red caída / API fuera
        log.warning("Open-Meteo no disponible -> clima sintético. %s", e)
        diario = _clima_sintetico(INICIO, FIN_CLIMA)
        fuente = "sintetico"

    diario["ym"] = diario["fecha"].dt.to_period("M")
    men = (
        diario.groupby("ym")
        .agg(
            lluvia_mm=("precipitation_sum", "sum"),
            temp_media=("temperature_2m_mean", "mean"),
        )
        .reset_index()
    )
    men["lluvia_mm"] = men["lluvia_mm"].round(1)
    men["temp_media"] = men["temp_media"].round(2)
    men["clima_fuente"] = fuente
    return men


def _clima_sintetico(start: str, end: str) -> pd.DataFrame:
    """Climatología diaria simple (solo si Open-Meteo no responde)."""
    dias = pd.date_range(start, end, freq="D")
    # Lluvia típica (mm/día aprox.) del Caribe panameño por mes.
    lluvia_mes = {
        1: 1.5, 2: 1.0, 3: 1.0, 4: 3.0, 5: 7.0, 6: 8.0,
        7: 8.0, 8: 8.5, 9: 8.0, 10: 9.5, 11: 9.0, 12: 4.0,
    }
    df = pd.DataFrame({"fecha": dias})
    df["precipitation_sum"] = df["fecha"].dt.month.map(lluvia_mes)
    df["temperature_2m_mean"] = 27.0
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = construir()
    print("\n== canal.parquet ==")
    print("Shape:", out.shape)
    print("Columnas:", list(out.columns))
    print("\nFuente (tránsitos):")
    print(out["fuente"].value_counts().to_string())
    print("\nClima fuente:")
    print(out["clima_fuente"].value_counts().to_string())
    print("\nHEAD:")
    print(out.head().to_string())
    print("\nTAIL:")
    print(out.tail().to_string())
