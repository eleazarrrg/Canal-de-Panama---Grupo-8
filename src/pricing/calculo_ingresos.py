"""Calcula ingresos mensuales estimados (peaje base + CAD + prima de subasta) por
tipo de esclusa.

Combina:
- transitos_panamax / transitos_neopanamax (data/processed/canal.parquet)
- nivel_lago_m (para el componente variable del CAD, mecanismo REAL de la ACP)
- peaje base ancla pública (data/raw/tarifas.csv, ver scraper_tarifas.py)
- prima de subasta de turnos preferenciales (dato REAL agregado FY2024, ver
  PRIMA_SUBASTA_FY2024_USD abajo — distribuida por mes con una clave estimada)

Fórmula (mecanismo documentado por la ACP, ver src/ingesta/scraper_tarifas.py):
    cad_variable_pct = interpolación lineal entre 10% (lago bajo) y 1% (lago alto)
    cad_usd_por_transito = CAD_FIJO + cad_variable_pct * peaje_base
    ingreso_por_transito = peaje_base + cad_usd_por_transito
    ingreso_mensual = transitos_del_mes * ingreso_por_transito
    ingreso_mensual_con_subasta = ingreso_mensual + prima_subasta_mes (solo FY2024)

--- Por qué existe la prima de subasta (dato real, no un ajuste inventado) ---
En el año fiscal 2024 (oct-2023 a sep-2024), la ACP reportó que los tránsitos
cayeron 9.2% y el tonelaje 13.1% por la sequía, pero los ingresos operativos
SUBIERON 1% (a B/.4,986 millones) en vez de caer los ~$800-850M que la propia
ACP había proyectado. La diferencia se explica en gran parte por un "ingreso
excepcional de aproximadamente $450 millones" de las subastas de turnos
preferenciales de cruce (navieras pagando extra para saltarse la fila cuando
escasearon los cupos), según declaró el vicepresidente de finanzas de la ACP.
Fuente: ACP, presentación de resultados financieros FY2024 (oct-2024);
cobertura: Infobae, Panamá América (25-oct-2024).

La ACP NO publica el desglose mensual de esos $450M, así que este script
reparte ese total real proporcionalmente entre los meses de FY2024 según qué
tan por debajo estuvo cada mes de su "tránsito normal" (promedio histórico del
mismo mes calendario, excluyendo FY2024): a mayor escasez de cupos, mayor
prima de subasta asumida ese mes. Es una distribución estimada de un TOTAL
real, no un dato mensual real — se documenta así para que quede claro qué
parte del número es verificable y cuál es un supuesto razonable.
"""
from __future__ import annotations

import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
PARQUET = ROOT / "data" / "processed" / "canal.parquet"
TARIFAS = ROOT / "data" / "raw" / "tarifas.csv"
OUT_PROCESSED = ROOT / "data" / "processed" / "ingresos.csv"
OUT_POWERBI = ROOT / "data" / "powerbi" / "FactIngresos.csv"

NIVEL_LAGO_BAJO_PIES = 79.0
NIVEL_LAGO_ALTO_PIES = 92.0
PIES_POR_METRO = 3.28084

# --- Ajuste real: prima de subastas de turnos preferenciales, FY2024 ---
# Total REAL reportado por la ACP (ver docstring). FY2024 = oct-2023 a sep-2024.
PRIMA_SUBASTA_FY2024_USD = 450_000_000
FY2024_INICIO = "2023-10-01"
FY2024_FIN = "2024-09-01"


def _metros_a_pies(m: float) -> float:
    return m * PIES_POR_METRO


def _cad_variable_pct(nivel_lago_m: float) -> float:
    """Interpola el % variable del CAD según el nivel del lago (mecanismo real, banda documentada)."""
    nivel_pies = _metros_a_pies(nivel_lago_m)
    nivel_pies = max(NIVEL_LAGO_BAJO_PIES, min(NIVEL_LAGO_ALTO_PIES, nivel_pies))
    # Más alto el lago -> menor %. Interpolación lineal entre las anclas.
    frac = (nivel_pies - NIVEL_LAGO_BAJO_PIES) / (NIVEL_LAGO_ALTO_PIES - NIVEL_LAGO_BAJO_PIES)
    return 0.10 - frac * (0.10 - 0.01)


def _distribuir_prima_subasta(df_total: pd.DataFrame) -> pd.DataFrame:
    """Reparte el total REAL de $450M (FY2024) entre los meses de FY2024,
    proporcional al déficit de tránsitos vs. el promedio histórico del mismo
    mes calendario (a mayor escasez, mayor prima asumida ese mes)."""
    d = df_total.copy()
    d["mes_num"] = pd.to_datetime(d["fecha"]).dt.month

    fuera_fy24 = d[(d["fecha"] < FY2024_INICIO) | (d["fecha"] > FY2024_FIN)]
    promedio_normal = fuera_fy24.groupby("mes_num")["transitos_total"].mean()

    en_fy24 = d[(d["fecha"] >= FY2024_INICIO) & (d["fecha"] <= FY2024_FIN)].copy()
    en_fy24["normal_esperado"] = en_fy24["mes_num"].map(promedio_normal)
    en_fy24["deficit"] = (en_fy24["normal_esperado"] - en_fy24["transitos_total"]).clip(lower=0)

    total_deficit = en_fy24["deficit"].sum()
    if total_deficit > 0:
        en_fy24["prima_subasta_usd"] = (
            en_fy24["deficit"] / total_deficit * PRIMA_SUBASTA_FY2024_USD
        )
    else:
        en_fy24["prima_subasta_usd"] = 0.0

    d = d.merge(en_fy24[["fecha", "prima_subasta_usd"]], on="fecha", how="left")
    d["prima_subasta_usd"] = d["prima_subasta_usd"].fillna(0.0)
    return d[["fecha", "prima_subasta_usd"]]


def calcular_ingresos(df: pd.DataFrame, tarifas: pd.DataFrame) -> pd.DataFrame:
    peaje = {r["tipo_esclusa"]: r["peaje_base_usd"] for _, r in tarifas.iterrows()}
    cad_fijo = tarifas["cad_fijo_usd"].iloc[0]

    d = df.copy()
    d["cad_variable_pct"] = d["nivel_lago_m"].apply(_cad_variable_pct)
    prima_por_mes = _distribuir_prima_subasta(df[["fecha", "transitos_total"]])

    filas = []
    for tipo, col in [("Panamax", "transitos_panamax"), ("Neopanamax", "transitos_neopanamax")]:
        base = peaje.get(tipo, 0)
        sub = d[["fecha", col, "cad_variable_pct", "fuente"]].copy()
        sub["tipo_esclusa"] = tipo
        sub["peaje_base_usd"] = base
        sub["cad_por_transito_usd"] = cad_fijo + sub["cad_variable_pct"] * base
        sub["ingreso_por_transito_usd"] = base + sub["cad_por_transito_usd"]
        sub["ingreso_mensual_usd"] = sub[col] * sub["ingreso_por_transito_usd"]
        sub = sub.rename(columns={col: "transitos", "fuente": "fuente_transitos"})
        sub["fuente_precio"] = "estimado_ancla_publica"
        filas.append(sub)

    out = pd.concat(filas, ignore_index=True)
    out = out.merge(prima_por_mes, on="fecha", how="left")

    # Reparto de la prima por mes entre Panamax/Neopanamax, proporcional a los
    # tránsitos de cada tipo ese mes.
    totales_mes = out.groupby("fecha")["transitos"].transform("sum").replace(0, pd.NA)
    out["prima_subasta_usd"] = (
        out["prima_subasta_usd"] * (out["transitos"] / totales_mes)
    ).fillna(0.0)
    out["ingreso_mensual_con_subasta_usd"] = out["ingreso_mensual_usd"] + out["prima_subasta_usd"]

    return out[["fecha", "tipo_esclusa", "transitos", "peaje_base_usd",
                "cad_variable_pct", "cad_por_transito_usd", "ingreso_por_transito_usd",
                "ingreso_mensual_usd", "prima_subasta_usd", "ingreso_mensual_con_subasta_usd",
                "fuente_transitos", "fuente_precio"]]


def main() -> None:
    df = pd.read_parquet(PARQUET).sort_values("fecha").reset_index(drop=True)
    if not TARIFAS.exists():
        raise SystemExit(
            f"No existe {TARIFAS}. Corré primero: python src/ingesta/scraper_tarifas.py"
        )
    tarifas = pd.read_csv(TARIFAS)

    ingresos = calcular_ingresos(df, tarifas)

    OUT_PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    ingresos.to_csv(OUT_PROCESSED, index=False)

    OUT_POWERBI.parent.mkdir(parents=True, exist_ok=True)
    fact = ingresos.copy()
    fact["fecha_id"] = pd.to_datetime(fact["fecha"]).dt.strftime("%Y%m").astype(int)
    fact["esclusa_id"] = fact["tipo_esclusa"].map({"Panamax": 1, "Neopanamax": 2})
    fact = fact.drop(columns=["fecha", "tipo_esclusa"])
    fact.to_csv(OUT_POWERBI, index=False)

    total = ingresos["ingreso_mensual_usd"].sum()
    total_con_subasta = ingresos["ingreso_mensual_con_subasta_usd"].sum()
    print(f"Ingresos calculados: {len(ingresos)} filas.")
    print(f"Ingreso total (peaje + CAD): ${total:,.0f} USD")
    print(f"Ingreso total (+ prima de subasta FY2024, dato real ${PRIMA_SUBASTA_FY2024_USD:,.0f}): "
          f"${total_con_subasta:,.0f} USD")
    print(f"Guardado en {OUT_PROCESSED} y {OUT_POWERBI}")


if __name__ == "__main__":
    main()
