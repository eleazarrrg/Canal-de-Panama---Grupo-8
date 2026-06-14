"""Ingesta de clima histórico REAL desde Open-Meteo (Fuente 2).

Open-Meteo Historical Weather API — gratis, sin API key.
Coordenadas de la zona del Lago Gatún (lat 9.18, lon -79.92).
"""
from __future__ import annotations

import pathlib

import pandas as pd
import requests

URL = "https://archive-api.open-meteo.com/v1/archive"
LAT, LON = 9.18, -79.92
RAW = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "clima.csv"


def obtener_clima(start: str, end: str) -> pd.DataFrame:
    """Descarga clima diario (lluvia y temperatura) entre start y end (YYYY-MM-DD).

    Devuelve un DataFrame diario con columnas: fecha, precipitation_sum,
    temperature_2m_mean. Guarda el crudo en data/raw/clima.csv.
    Lanza requests.RequestException si no hay red o la API falla.
    """
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": start,
        "end_date": end,
        "daily": "precipitation_sum,temperature_2m_mean",
        "timezone": "America/Panama",
    }
    r = requests.get(URL, params=params, timeout=60)
    r.raise_for_status()
    d = r.json()["daily"]

    df = pd.DataFrame(
        {
            "fecha": pd.to_datetime(d["time"]),
            "precipitation_sum": d["precipitation_sum"],
            "temperature_2m_mean": d["temperature_2m_mean"],
        }
    )
    RAW.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW, index=False)
    return df


if __name__ == "__main__":
    out = obtener_clima("2014-10-01", "2025-09-30")
    print(out.head())
    print(f"{len(out)} días descargados -> {RAW}")
