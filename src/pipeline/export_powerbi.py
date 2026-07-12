"""Exporta el dataset y el pronóstico a un modelo estrella (star schema)
para Power BI.

Genera en data/powerbi/:
    DimFecha.csv        -- una fila por mes, atributos de calendario
    DimEsclusa.csv       -- catálogo de tipos de esclusa (Panamax / Neopanamax)
    FactTransitos.csv    -- hechos mensuales por tipo de esclusa (formato largo)
    FactClima.csv         -- hechos de clima mensual (grano: mes)
    FactPronostico.csv    -- pronóstico FY2026 con banda de intervalo

(FactIngresos.csv lo genera src/pricing/calculo_ingresos.py, no este script; usa
las mismas claves fecha_id/esclusa_id para unirse al modelo estrella.)

Diseño (grano y relaciones):

    DimFecha (fecha_id) 1───* FactTransitos (fecha_id, esclusa_id)
    DimEsclusa (esclusa_id) 1───* FactTransitos
    DimFecha (fecha_id) 1───* FactClima (fecha_id)      [grano: mes, sin esclusa]
    DimFecha (fecha_id) 1───* FactPronostico (fecha_id)

FactTransitos está en formato largo (una fila por mes x tipo de esclusa) para
que las medidas DAX (SUM, promedios, %) funcionen de forma nativa sin tener
que desagregar columnas anchas en Power Query.

Uso:
    python src/pipeline/export_powerbi.py
"""
from __future__ import annotations

import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
PARQUET = ROOT / "data" / "processed" / "canal.parquet"
PRONOSTICO = ROOT / "models" / "pronostico.csv"
OUT_DIR = ROOT / "data" / "powerbi"

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre",
    12: "Diciembre",
}
# Trimestre fiscal ACP (año fiscal empieza en octubre): oct-dic=T1, ene-mar=T2,
# abr-jun=T3, jul-sep=T4. Ver _trimestre_fiscal().


def _trimestre_fiscal(mes: int) -> str:
    if mes in (10, 11, 12):
        return "T1"
    if mes in (1, 2, 3):
        return "T2"
    if mes in (4, 5, 6):
        return "T3"
    return "T4"  # jul, ago, sep


def construir_dim_fecha(fechas: pd.Series) -> pd.DataFrame:
    d = pd.DataFrame({"fecha": pd.to_datetime(fechas.unique())}).sort_values("fecha")
    d["fecha_id"] = d["fecha"].dt.strftime("%Y%m").astype(int)
    d["anio"] = d["fecha"].dt.year
    d["mes_num"] = d["fecha"].dt.month
    d["mes_nombre"] = d["mes_num"].map(MESES_ES)
    d["anio_fiscal"] = d.apply(
        lambda r: r["anio"] + 1 if r["mes_num"] >= 10 else r["anio"], axis=1
    )
    d["trimestre_fiscal"] = d["mes_num"].map(_trimestre_fiscal)
    d["etiqueta"] = d["mes_nombre"].str[:3] + "-" + d["anio"].astype(str)
    return d[["fecha_id", "fecha", "anio", "mes_num", "mes_nombre",
              "anio_fiscal", "trimestre_fiscal", "etiqueta"]]


def construir_dim_esclusa() -> pd.DataFrame:
    return pd.DataFrame([
        {"esclusa_id": 1, "esclusa_nombre": "Panamax", "generacion": "Original (1914)"},
        {"esclusa_id": 2, "esclusa_nombre": "Neopanamax", "generacion": "Ampliación (2016)"},
    ])


def construir_fact_transitos(df: pd.DataFrame, dim_fecha: pd.DataFrame) -> pd.DataFrame:
    base = df.merge(dim_fecha[["fecha_id", "fecha"]], on="fecha", how="left")
    panamax = base[["fecha_id", "transitos_panamax", "tonelaje_panamax", "fuente"]].copy()
    panamax["esclusa_id"] = 1
    panamax = panamax.rename(columns={"transitos_panamax": "transitos",
                                      "tonelaje_panamax": "tonelaje"})
    neopanamax = base[["fecha_id", "transitos_neopanamax", "tonelaje_neopanamax", "fuente"]].copy()
    neopanamax["esclusa_id"] = 2
    neopanamax = neopanamax.rename(columns={"transitos_neopanamax": "transitos",
                                            "tonelaje_neopanamax": "tonelaje"})
    fact = pd.concat([panamax, neopanamax], ignore_index=True)
    return fact[["fecha_id", "esclusa_id", "transitos", "tonelaje", "fuente"]]


def construir_fact_clima(df: pd.DataFrame, dim_fecha: pd.DataFrame) -> pd.DataFrame:
    base = df.merge(dim_fecha[["fecha_id", "fecha"]], on="fecha", how="left")
    base["lluvia_acum_12m"] = base.sort_values("fecha")["lluvia_mm"].rolling(12).sum()
    cols = ["fecha_id", "lluvia_mm", "lluvia_acum_12m", "temp_media",
            "nivel_lago_m", "clima_fuente"]
    return base[cols]


def construir_fact_pronostico(dim_fecha: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    if not PRONOSTICO.exists():
        return None
    fc = pd.read_csv(PRONOSTICO, parse_dates=["fecha"])
    fc["fecha_id"] = fc["fecha"].dt.strftime("%Y%m").astype(int)
    # Si el mes del pronóstico no está en DimFecha (es futuro), lo agregamos.
    faltantes = fc.loc[~fc["fecha_id"].isin(dim_fecha["fecha_id"]), "fecha"]
    if not faltantes.empty:
        extra = construir_dim_fecha(faltantes)
        dim_fecha = pd.concat([dim_fecha, extra], ignore_index=True)
    cols = [c for c in ["fecha_id", "pred", "lo", "hi"] if c in fc.columns]
    return fc[cols], dim_fecha


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(PARQUET).sort_values("fecha").reset_index(drop=True)

    dim_fecha = construir_dim_fecha(df["fecha"])
    dim_esclusa = construir_dim_esclusa()
    fact_pronostico_resultado = construir_fact_pronostico(dim_fecha)
    if fact_pronostico_resultado is not None:
        fact_pronostico, dim_fecha = fact_pronostico_resultado
    else:
        fact_pronostico = None

    fact_transitos = construir_fact_transitos(df, dim_fecha)
    fact_clima = construir_fact_clima(df, dim_fecha)

    dim_fecha.to_csv(OUT_DIR / "DimFecha.csv", index=False)
    dim_esclusa.to_csv(OUT_DIR / "DimEsclusa.csv", index=False)
    fact_transitos.to_csv(OUT_DIR / "FactTransitos.csv", index=False)
    fact_clima.to_csv(OUT_DIR / "FactClima.csv", index=False)
    if fact_pronostico is not None:
        fact_pronostico.to_csv(OUT_DIR / "FactPronostico.csv", index=False)

    print(f"Exportado a {OUT_DIR}:")
    for f in sorted(OUT_DIR.glob("*.csv")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
