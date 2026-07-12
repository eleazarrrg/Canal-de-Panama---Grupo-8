"""Dashboard del Canal de Panamá — agua -> capacidad -> tránsitos.

Páginas: Resumen, Tendencias, Agua vs. Tránsitos, Mapa, Pronóstico.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.llm.resumen import generar_resumen

PARQUET = ROOT / "data" / "processed" / "canal.parquet"
METRICAS = ROOT / "models" / "metricas.json"
PRONOSTICO = ROOT / "models" / "pronostico.csv"
PRONOSTICO_META = ROOT / "models" / "pronostico.json"
INGRESOS = ROOT / "data" / "processed" / "ingresos.csv"

# Referencia pública externa para el chequeo out-of-sample del pronóstico:
# tránsitos reales ACP FY2026 a may-2026 (BASE ALTO CALADO, métrica distinta a
# transitos_total = panamax + neopanamax). No se usa para entrenar.
ACP_FY2026_ALTO_CALADO = 8593

NOMBRE_SERIE = {
    "Ambas (total)": "transitos_total",
    "Panamax": "transitos_panamax",
    "Neopanamax": "transitos_neopanamax",
}

PUNTOS_CANAL = {
    "Entrada Atlántico (Cristóbal/Colón)": (9.36, -79.92),
    "Esclusas de Gatún": (9.27, -79.92),
    "Esclusas de Agua Clara": (9.28, -79.90),
    "Lago Gatún": (9.20, -79.85),
    "Esclusas de Pedro Miguel": (9.02, -79.61),
    "Esclusas de Miraflores": (9.00, -79.59),
    "Esclusas de Cocolí": (8.98, -79.59),
    "Entrada Pacífico (Balboa)": (8.95, -79.56),
}


@st.cache_data
def cargar_datos() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET).sort_values("fecha").reset_index(drop=True)
    df["lluvia_acum_12m"] = df["lluvia_mm"].rolling(12).sum()
    return df


@st.cache_data
def cargar_metricas() -> dict:
    return json.loads(METRICAS.read_text(encoding="utf-8")) if METRICAS.exists() else {}


@st.cache_data
def cargar_pronostico():
    if not PRONOSTICO.exists():
        return None, {}
    fc = pd.read_csv(PRONOSTICO, parse_dates=["fecha"])
    meta = json.loads(PRONOSTICO_META.read_text(encoding="utf-8")) if PRONOSTICO_META.exists() else {}
    return fc, meta

@st.cache_data
def cargar_ingresos() -> pd.DataFrame:
    if not INGRESOS.exists():
        return pd.DataFrame()
    ing = pd.read_csv(INGRESOS, parse_dates=["fecha"])
    return ing.groupby("fecha", as_index=False)[
        ["ingreso_mensual_usd", "prima_subasta_usd", "ingreso_mensual_con_subasta_usd"]
    ].sum()

def filtrar(df: pd.DataFrame, rango) -> pd.DataFrame:
    ini, fin = rango
    m = (df["fecha"] >= pd.Timestamp(ini)) & (df["fecha"] <= pd.Timestamp(fin))
    return df[m].copy()


def _variacion(df_full: pd.DataFrame, fecha, col):
    """Variación interanual robusta (busca el mismo mes del año anterior en todo el historial)."""
    prev = df_full[df_full["fecha"] == fecha - pd.DateOffset(years=1)]
    cur = df_full[df_full["fecha"] == fecha]
    if prev.empty or cur.empty or not prev.iloc[0][col]:
        return None
    return (cur.iloc[0][col] - prev.iloc[0][col]) / prev.iloc[0][col] * 100


# ----------------------------- Páginas -----------------------------

def pagina_resumen(df, df_full, fc, serie_col, serie_label):
    st.header("Resumen ejecutivo")
    if df.empty:
        st.warning("Sin datos en el rango seleccionado.")
        return

    ult = df.iloc[-1]
    var = _variacion(df_full, ult["fecha"], serie_col)
    var_total = _variacion(df_full, ult["fecha"], "transitos_total")

    pron_val, pron_txt = None, "—"
    if fc is not None and not fc.empty:
        p3 = fc.head(3)
        pron_val = int(p3["pred"].mean())
        pron_txt = (f"un promedio de ~{pron_val:,} tránsitos/mes "
                    f"(rango {int(p3['lo'].min()):,}–{int(p3['hi'].max()):,})")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Tránsitos último mes · {serie_label}", f"{int(ult[serie_col]):,}",
              help=f"Mes: {ult['fecha'].date()}")
    c2.metric("Variación interanual", f"{var:+.1f}%" if var is not None else "—")
    c3.metric("Nivel Lago Gatún (contexto)", f"{ult['nivel_lago_m']:.2f} m")
    c4.metric("Pronóstico (prom. próx. 3m)", f"{pron_val:,}" if pron_val is not None else "—")

    st.caption("Clima real (Open-Meteo); tránsitos mensuales estimados sobre controles "
               "anuales reales de la ACP (ver README).")

    st.subheader("Resumen ejecutivo (LLM)")
    stats = {
        "transitos": f"{int(ult['transitos_total']):,}",
        "variacion": f"{var_total:+.1f}%" if var_total is not None else "s/d",
        "nivel": f"{ult['nivel_lago_m']:.2f}",
        "lluvia_acum": f"{ult['lluvia_acum_12m']:.0f}" if pd.notna(ult["lluvia_acum_12m"]) else "s/d",
        "pronostico": pron_txt,
    }
    try:
        key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        key = None
    if st.button("Regenerar resumen") or "resumen_txt" not in st.session_state:
        st.session_state["resumen_txt"] = generar_resumen(stats, key)
    st.write(st.session_state["resumen_txt"])
    if not key:
        st.caption("Sin `GEMINI_API_KEY`: resumen por plantilla local (degradación). "
                   "Agregá la clave en `.streamlit/secrets.toml` para usar Gemini.")
    ingresos_df = cargar_ingresos()
    if not ingresos_df.empty:
        ing_filtrado = ingresos_df[(ingresos_df["fecha"] >= df["fecha"].min()) &
                                    (ingresos_df["fecha"] <= df["fecha"].max())]
        ing_ult = (ing_filtrado["ingreso_mensual_con_subasta_usd"].iloc[-1]
                if not ing_filtrado.empty else None)
        ing_prom = (ing_filtrado["ingreso_mensual_con_subasta_usd"].mean()
                    if not ing_filtrado.empty else None)

        c11, c12 = st.columns(2)
        c11.metric("Ingreso estimado último mes", f"${ing_ult:,.0f}" if ing_ult else "—",
                help="Peaje base (ancla pública) + CAD (real ACP) + prima de subasta FY2024 "
                        "(total real $450M, repartido por mes de forma estimada). "
                        "Ver docs/METODOLOGIA_PRECIOS.md")
        c12.metric("Ingreso promedio mensual (rango)", f"${ing_prom:,.0f}" if ing_prom else "—")


def pagina_tendencias(df, serie_col, serie_label):
    st.header("Tendencias mensuales")
    if df.empty:
        st.warning("Sin datos en el rango seleccionado.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["fecha"], y=df[serie_col], mode="lines",
                             name=f"Tránsitos ({serie_label})", line=dict(color="#1f77b4")))
    fig.update_layout(height=380, margin=dict(t=50, b=10),
                      title=f"Tránsitos mensuales — {serie_label}",
                      yaxis_title="Tránsitos / mes", xaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df["fecha"], y=df["tonelaje"] / 1e6, mode="lines",
                              name="Tonelaje CP/SUAB", line=dict(color="#2ca02c")))
    fig2.update_layout(height=340, margin=dict(t=50, b=10),
                       title="Tonelaje CP/SUAB mensual",
                       yaxis_title="Tonelaje CP/SUAB (millones)", xaxis_title=None)
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("Tonelaje en toneladas **CP/SUAB** (sistema de arqueo del Canal), no toneladas largas.")


def pagina_agua(df):
    st.header("Agua vs. Tránsitos")
    st.markdown("**Tesis:** el agua disponible (lluvia acumulada → Lago Gatún) marca la "
                "capacidad de tránsito. La sequía 2023–2024 lo hizo visible.")
    d = df.dropna(subset=["lluvia_acum_12m"])
    if len(d) < 12:
        st.warning("Rango muy corto para la correlación acumulada de 12 meses. Amplía el rango.")
        return

    r_acum = d["lluvia_acum_12m"].corr(d["transitos_total"])
    r_mes = df["lluvia_mm"].corr(df["transitos_total"])
    c1, c2 = st.columns(2)
    c1.metric("r · lluvia acum. 12m ↔ tránsitos", f"{r_acum:+.2f}",
              help="Hallazgo principal (bivariado, sin rezago). Mecanismo: balance hídrico anual.")
    c2.metric("r · lluvia mensual ↔ tránsitos", f"{r_mes:+.2f}",
              help="Contraste: el mes individual es ruido estacional (≈0).")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["fecha"], y=df["transitos_total"], name="Tránsitos",
                             line=dict(color="#1f77b4")))
    fig.add_trace(go.Scatter(x=df["fecha"], y=df["lluvia_acum_12m"], name="Lluvia acum. 12m (mm)",
                             yaxis="y2", line=dict(color="#17becf", dash="dot")))
    fig.update_layout(height=420, margin=dict(t=50, b=10),
                      title="Tránsitos vs. lluvia acumulada 12m",
                      legend=dict(orientation="h", yanchor="bottom", y=-0.25),
                      yaxis=dict(title="Tránsitos / mes"),
                      yaxis2=dict(title="Lluvia acum. 12m (mm)", overlaying="y", side="right"))
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=d["lluvia_acum_12m"], y=d["transitos_total"], mode="markers",
                              name="meses", marker=dict(color="#1f77b4", opacity=0.6)))
    m, b = np.polyfit(d["lluvia_acum_12m"], d["transitos_total"], 1)
    xs = np.array([d["lluvia_acum_12m"].min(), d["lluvia_acum_12m"].max()])
    fig2.add_trace(go.Scatter(x=xs, y=m * xs + b, mode="lines", name="ajuste",
                              line=dict(color="#d62728")))
    fig2.update_layout(height=380, margin=dict(t=50, b=10),
                       title="Lluvia acum. 12m vs. tránsitos (dispersión + ajuste)",
                       xaxis_title="Lluvia acumulada 12m (mm)", yaxis_title="Tránsitos / mes")
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("Nota exploratoria — rezago operativo (no usado como variable)"):
        mejor_r, mejor_lag = r_acum, 0
        for lag in range(1, 9):
            rr = d["lluvia_acum_12m"].shift(lag).corr(d["transitos_total"])
            if pd.notna(rr) and rr > mejor_r:
                mejor_r, mejor_lag = rr, lag
        st.write(f"Con un rezago de ~{mejor_lag} meses la correlación sube a **{mejor_r:+.2f}**, "
                 "consistente con el retraso déficit → recorte de cupos (el lago integra el "
                 "déficit antes de afectar la capacidad).")
        st.warning("Es **exploratorio**: el rezago óptimo se ajusta sobre un único episodio de "
                   "sequía (n=1), así que NO se usa como feature ni como cifra principal.")

    met = cargar_metricas()
    imp = met.get("importancia", {}).get("lluvia_acum_12m")
    if imp is not None:
        st.caption(f"Apoyo (no prueba): en el modelo, `lluvia_acum_12m` es la 2ª variable más "
                   f"importante ({imp:.0%}), detrás de la autocorrelación `lag1`.")
    st.caption("El nivel del Lago Gatún correlaciona alto con los tránsitos, pero por "
               "construcción del respaldo (mismo calendario) → se usa solo como **contexto**.")


def pagina_mapa():
    st.header("Mapa del Canal")
    st.caption("Infraestructura clave, del Atlántico (norte) al Pacífico (sur).")
    try:
        import folium
        from streamlit_folium import st_folium
    except Exception:
        st.error("Faltan `folium` / `streamlit-folium`. Instalá `requirements.txt`.")
        return

    lats = [c[0] for c in PUNTOS_CANAL.values()]
    lons = [c[1] for c in PUNTOS_CANAL.values()]
    m = folium.Map(location=[sum(lats) / len(lats), sum(lons) / len(lons)], zoom_start=10)
    folium.PolyLine(list(PUNTOS_CANAL.values()), color="#1f77b4", weight=2, opacity=0.6).add_to(m)
    for nombre, (lat, lon) in PUNTOS_CANAL.items():
        folium.Marker([lat, lon], tooltip=nombre, popup=nombre,
                      icon=folium.Icon(color="blue", icon="anchor", prefix="fa")).add_to(m)
    st_folium(m, use_container_width=True, height=520, returned_objects=[])


def pagina_pronostico(df_full, fc, meta):
    st.header("Pronóstico de tránsitos — FY2026")
    if fc is None or fc.empty:
        st.warning("Falta `models/pronostico.csv`. Generalo con `python src/ml/forecast.py`.")
        return

    fc = fc.copy()
    real = fc[fc["lluvia_fuente"] == "real"]
    clim = fc[fc["lluvia_fuente"] == "climatologia"]
    if not real.empty and not clim.empty:
        clim = pd.concat([real.tail(1), clim], ignore_index=True)  # conecta las dos trazas

    hist = df_full.tail(24)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(fc["fecha"]) + list(fc["fecha"][::-1]),
                             y=list(fc["hi"]) + list(fc["lo"][::-1]),
                             fill="toself", fillcolor="rgba(214,39,40,0.15)",
                             line=dict(width=0), name="Intervalo aprox.", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=hist["fecha"], y=hist["transitos_total"],
                             name="Histórico (total)", line=dict(color="#1f77b4")))
    fig.add_trace(go.Scatter(x=real["fecha"], y=real["pred"],
                             name="Pronóstico (lluvia real, hasta may-2026)",
                             line=dict(color="#d62728")))
    fig.add_trace(go.Scatter(x=clim["fecha"], y=clim["pred"],
                             name="Pronóstico (lluvia = climatología, jun–sep 2026)",
                             line=dict(color="#d62728", dash="dot")))
    prom_real = ACP_FY2026_ALTO_CALADO / 8  # oct25-may26 = 8 meses
    fig.add_trace(go.Scatter(x=[pd.Timestamp("2025-10-01"), pd.Timestamp("2026-05-01")],
                             y=[prom_real, prom_real], mode="lines",
                             name="ACP real FY2026 (alto calado, prom. mensual) — solo chequeo de forma",
                             line=dict(color="#7f7f7f", dash="dash")))
    fig.update_layout(height=470, margin=dict(t=50, b=10),
                      title="Histórico (24m) + pronóstico FY2026",
                      yaxis_title="Tránsitos / mes",
                      legend=dict(orientation="h", yanchor="bottom", y=-0.45))
    st.plotly_chart(fig, use_container_width=True)

    rmse = meta.get("rmse_recursivo_fy2025")
    if rmse:
        st.caption(f"Banda = pred ± 1.96 · RMSE recursivo (backtest FY2025, RMSE = {rmse}). "
                   "Es **aproximada y probablemente subestima** la incertidumbre real, porque la "
                   "serie objetivo es suave por construcción del respaldo.")

    parc = int(fc[fc["fecha"] <= "2026-05-01"]["pred"].sum())
    dif = parc - ACP_FY2026_ALTO_CALADO
    c1, c2, c3 = st.columns(3)
    c1.metric("Pronóstico acum. oct25–may26 (base total)", f"{parc:,}")
    c2.metric("ACP real oct25–may26 (alto calado)", f"{ACP_FY2026_ALTO_CALADO:,}")
    c3.metric("Diferencia de base (no error)", f"{dif:+,}")
    st.caption("Chequeo out-of-sample, con honestidad: las dos cifras **no son comparables en "
               "nivel** (distinta base). Los ~470 de diferencia son la cuota de naves que el "
               "conteo de *alto calado* no incluye — diferencia de base, **no error del modelo**. "
               "Que coincidan en orden es **corroboración sobre un período** (n=1, FY2026 estable), "
               "**no prueba de skill general**.")

    with st.expander("Ver tabla del pronóstico (lluvia: real vs climatología)"):
        t = fc.copy()
        t["fecha"] = t["fecha"].dt.strftime("%Y-%m")
        st.dataframe(t, use_container_width=True)


# ----------------------------- App -----------------------------

def main():
    st.set_page_config(page_title="Canal de Panamá — Tránsitos", layout="wide")
    if not PARQUET.exists():
        st.error("Falta `data/processed/canal.parquet`. Generalo con "
                 "`python src/pipeline/build_dataset.py`.")
        st.stop()
    df_full = cargar_datos()
    fc, fc_meta = cargar_pronostico()

    st.sidebar.title("Canal de Panamá")
    pagina = st.sidebar.radio("Página",
                              ["Resumen", "Tendencias", "Agua vs. Tránsitos", "Mapa", "Pronóstico"])

    st.sidebar.subheader("Filtros")
    meses = [d.strftime("%Y-%m") for d in df_full["fecha"]]
    rango = st.sidebar.select_slider("Rango de fechas", options=meses,
                                     value=(meses[0], meses[-1]))
    serie_label = st.sidebar.radio("Tipo de esclusa", list(NOMBRE_SERIE.keys()))
    serie_col = NOMBRE_SERIE[serie_label]

    df = filtrar(df_full, (pd.Timestamp(rango[0]), pd.Timestamp(rango[1])))
    st.sidebar.caption(
        f"{len(df)} meses · {df['fecha'].min().date()} → {df['fecha'].max().date()}"
        if not df.empty else "Rango vacío"
    )
    if pagina in ("Mapa", "Pronóstico"):
        st.sidebar.caption("(Mapa y Pronóstico no dependen de los filtros.)")

    if pagina == "Resumen":
        pagina_resumen(df, df_full, fc, serie_col, serie_label)
    elif pagina == "Tendencias":
        pagina_tendencias(df, serie_col, serie_label)
    elif pagina == "Agua vs. Tránsitos":
        pagina_agua(df)
    elif pagina == "Mapa":
        pagina_mapa()
    else:
        pagina_pronostico(df_full, fc, fc_meta)


if __name__ == "__main__":
    main()
