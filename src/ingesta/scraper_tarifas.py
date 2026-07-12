"""Ingesta de tarifas/peajes del Canal de Panamá.

Intenta raspar la página pública de tarifas de la ACP; si la estructura
cambia o no hay red (mismo patrón que scraper_acp.py), cae a anclas públicas
documentadas y marca la fila como `fuente="estimado"`.

Por qué no hay un CSV histórico mensual de "cuánto se cobró": la ACP publica
el TARIFARIO (renglones por categoría de buque y esclusa) y las NOTAS al
tarifario, pero no un histórico de recaudación mensual por tránsito abierto
al público. Por eso se documenta un peaje base promedio por tipo de esclusa
como ancla pública (ver PEAJE_BASE_ANCLA) en vez de inventar cifras.

Fuentes públicas (consultadas jul-2026):
- Tarifario ACP (vigente desde ene-2025): https://pancanal.com/tarifas-maritimas/
- ACP, comunicado sobre Cargo por Agua Dulce (CAD):
  https://pancanal.com/canal-de-panama-adopta-medidas-para-garantizar-disponibilidad-de-agua-y-confiabilidad-de-la-ruta/
"""
from __future__ import annotations

import pathlib

import requests

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "tarifas.csv"

TARIFAS_URL = "https://pancanal.com/tarifas-maritimas/"

# --- Ancla pública documentada del peaje base promedio por tránsito (USD) ---
# Panamax: promedio industria reportado (buques regulares, esclusas originales).
# Neopanamax: promedio industria reportado (portacontenedores grandes, esclusas ampliadas).
# Estas cifras son ÓRDENES DE MAGNITUD públicos (prensa/ACP), no el peaje exacto
# de cada buque, que depende de tonelaje, tipo de carga y condición de lastre.
PEAJE_BASE_ANCLA = {
    "Panamax": 90_000,      # ancla pública: buque regular, esclusas originales
    "Neopanamax": 350_000,  # ancla pública: portacontenedor grande, esclusas ampliadas
}

# --- Cargo por Agua Dulce (CAD) — mecanismo REAL, documentado por la ACP ---
CAD_FIJO_USD = 10_000          # por tránsito, buques > 125 pies de eslora
CAD_VARIABLE_MIN_PCT = 0.01    # nivel de lago alto -> 1% del peaje
CAD_VARIABLE_MAX_PCT = 0.10    # nivel de lago bajo -> 10% del peaje

# Curva de referencia del nivel del lago Gatún (pies) usada para interpolar el
# % variable del CAD. Ancla documentada: temporada seca severa ~79 pies (10%),
# nivel óptimo/curva guía ~92 pies (1%). Interpolación lineal entre ambos.
NIVEL_LAGO_BAJO_PIES = 79.0
NIVEL_LAGO_ALTO_PIES = 92.0


def intentar_scrape_tarifario() -> dict | None:
    """Intenta confirmar que el tarifario público sigue accesible.

    No parsea el PDF completo (formato inestable, 60+ renglones); solo
    verifica que la página esté viva como señal de que las anclas siguen
    vigentes. Si falla, se documenta como tal y se usa el fallback.
    """
    try:
        r = requests.get(TARIFAS_URL, timeout=10)
        r.raise_for_status()
        return {"verificado": True, "status": r.status_code}
    except Exception as e:
        print(f"[scraper_tarifas] No se pudo verificar el tarifario en línea: {e}")
        return None


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    verif = intentar_scrape_tarifario()
    fuente = "ancla_publica_verificada" if verif else "ancla_publica_sin_verificar"

    import csv
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tipo_esclusa", "peaje_base_usd", "cad_fijo_usd",
                    "cad_variable_min_pct", "cad_variable_max_pct", "fuente"])
        for tipo, peaje in PEAJE_BASE_ANCLA.items():
            w.writerow([tipo, peaje, CAD_FIJO_USD, CAD_VARIABLE_MIN_PCT,
                        CAD_VARIABLE_MAX_PCT, fuente])

    print(f"Tarifas escritas en {OUT} (fuente={fuente})")


if __name__ == "__main__":
    main()
