"""Scraper de estadísticas de tránsito de la ACP (Fuente 1).

Intenta obtener totales ANUALES (por año fiscal) de tránsitos oceaneros
desde fuentes públicas (pancanal.com / Portal Logístico de Panamá).

El detalle MENSUAL que no exista en las fuentes queda como 'estimado' en el
pipeline (ver fallback.py / build_dataset.py): nunca se inventa.

Si no logra extraer datos utilizables, lanza ScraperACPError para que el
pipeline use los anclajes públicos documentados.
"""
from __future__ import annotations

import logging
import pathlib
import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

RAW = pathlib.Path(__file__).resolve().parents[2] / "data" / "raw" / "transitos.csv"

FUENTES = [
    "https://pancanal.com/estadisticas/",
    "https://pancanal.com/transparencia/",
    "https://logistics.gatech.pa/",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (proyecto-academico-UTP analisis-canal)"}


class ScraperACPError(Exception):
    """Se lanza cuando no se pueden extraer datos reales de tránsito."""


def obtener_transitos() -> pd.DataFrame:
    """Intenta raspar totales anuales de tránsitos de la ACP.

    Devuelve un DataFrame [anio_fiscal, transitos_total] si tiene éxito y lo
    guarda en data/raw/transitos.csv. Si falla, lanza ScraperACPError.
    """
    registros: list[dict] = []
    for url in FUENTES:
        try:
            html = _descargar(url)
        except requests.RequestException as e:
            log.warning("No se pudo acceder a %s: %s", url, e)
            continue
        registros += _parsear_totales_anuales(html)
        if registros:
            log.info("Datos hallados en %s", url)
            break

    if not registros:
        raise ScraperACPError(
            "No se hallaron totales de tránsito en las fuentes ACP/GT "
            "(estructura del sitio cambió o sin red). El pipeline usará los "
            "anclajes públicos documentados."
        )

    df = (
        pd.DataFrame(registros)
        .drop_duplicates("anio_fiscal")
        .sort_values("anio_fiscal")
        .reset_index(drop=True)
    )
    RAW.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW, index=False)
    return df


def _descargar(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def _parsear_totales_anuales(html: str) -> list[dict]:
    """Busca pares (año fiscal, total de tránsitos) en el HTML.

    Heurística deliberadamente conservadora: solo acepta números en un rango
    plausible (8.000–16.000 tránsitos/año). Si la estructura del sitio cambia,
    devuelve [] y el pipeline cae al respaldo en vez de inventar datos.
    """
    soup = BeautifulSoup(html, "lxml")
    texto = soup.get_text(" ", strip=True)
    encontrados = []
    patron = r"(?:FY|AÑO FISCAL|FISCAL YEAR)?\s*(20\d{2}).{0,40}?([0-9]{1,2}[.,][0-9]{3})"
    for m in re.finditer(patron, texto):
        anio = int(m.group(1))
        total = int(m.group(2).replace(".", "").replace(",", ""))
        if 2010 <= anio <= 2030 and 8000 <= total <= 16000:
            encontrados.append({"anio_fiscal": anio, "transitos_total": total})
    return encontrados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        print(obtener_transitos())
    except ScraperACPError as e:
        print("Scraper falló (esperado si cambió el sitio):", e)
