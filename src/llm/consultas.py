"""Consultas en lenguaje natural sobre el dataset del Canal, vía Gemini.

Estrategia: en vez de dejar que el LLM "invente" cifras, se le pasa un
resumen estadístico compacto del rango de datos filtrado (no el dataset
completo, para no gastar tokens ni arriesgar alucinaciones con datos crudos)
y se le pide que responda SOLO con esa evidencia. Si no hay API key, cae a
una respuesta local basada en reglas simples (degradación, igual que
`resumen.py`).

Uso típico desde app.py:

    from src.llm.consultas import responder_pregunta
    resp = responder_pregunta("¿Cuál fue el mes con más tránsitos en 2024?", df, key)
"""
from __future__ import annotations

import pandas as pd


def _resumen_estadistico(df: pd.DataFrame) -> str:
    """Compacta el dataframe filtrado en una tabla de texto que cabe en el prompt."""
    d = df.copy()
    d["fecha"] = pd.to_datetime(d["fecha"]).dt.strftime("%Y-%m")
    cols = ["fecha", "transitos_total", "transitos_panamax", "transitos_neopanamax",
            "tonelaje", "nivel_lago_m", "lluvia_mm"]
    cols = [c for c in cols if c in d.columns]
    filas = d[cols].to_csv(index=False)
    extremos = (
        f"Mes con más tránsitos: {d.loc[d['transitos_total'].idxmax(), 'fecha']} "
        f"({int(d['transitos_total'].max())}).\n"
        f"Mes con menos tránsitos: {d.loc[d['transitos_total'].idxmin(), 'fecha']} "
        f"({int(d['transitos_total'].min())}).\n"
        f"Promedio del período: {d['transitos_total'].mean():.0f}.\n"
    )
    return f"{extremos}\nDatos mensuales (CSV):\n{filas}"


def _respuesta_local(pregunta: str, df: pd.DataFrame) -> str:
    """Fallback sin API key: heurística simple sobre máximos/mínimos/promedios."""
    d = df.copy()
    d["fecha_str"] = pd.to_datetime(d["fecha"]).dt.strftime("%B %Y")
    p = pregunta.lower()
    if "máx" in p or "mayor" in p or "más tránsitos" in p or "pico" in p:
        fila = d.loc[d["transitos_total"].idxmax()]
        return (f"El mes con más tránsitos fue {fila['fecha_str']}, con "
                f"{int(fila['transitos_total']):,} tránsitos. "
                f"(Respuesta generada localmente — sin GEMINI_API_KEY configurada.)")
    if "mín" in p or "menor" in p or "menos tránsitos" in p or "peor" in p:
        fila = d.loc[d["transitos_total"].idxmin()]
        return (f"El mes con menos tránsitos fue {fila['fecha_str']}, con "
                f"{int(fila['transitos_total']):,} tránsitos. "
                f"(Respuesta generada localmente — sin GEMINI_API_KEY configurada.)")
    if "promedio" in p or "media" in p:
        return (f"El promedio de tránsitos en el rango seleccionado es "
                f"{d['transitos_total'].mean():.0f} por mes. "
                f"(Respuesta generada localmente — sin GEMINI_API_KEY configurada.)")
    return ("No tengo una clave de Gemini configurada, así que solo puedo responder "
            "preguntas simples de máximo, mínimo o promedio. Agregá GEMINI_API_KEY "
            "en `.streamlit/secrets.toml` para consultas libres en lenguaje natural.")


def responder_pregunta(pregunta: str, df: pd.DataFrame, api_key: str | None) -> str:
    """Responde una pregunta en lenguaje natural sobre `df` (ya filtrado por la UI)."""
    if not api_key:
        return _respuesta_local(pregunta, df)

    try:
        from google import genai
    except ImportError:
        return _respuesta_local(pregunta, df)

    contexto = _resumen_estadistico(df)
    prompt = f"""Sos un analista de datos del Canal de Panamá. Respondé la pregunta
del usuario usando ÚNICAMENTE los datos de la tabla de abajo. Si la pregunta
no se puede responder con estos datos, decilo explícitamente en vez de
inventar una cifra. Respondé en español, en un máximo de 4 líneas, sin
repetir toda la tabla.

DATOS:
{contexto}

PREGUNTA: {pregunta}
"""
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-flash-latest",  # mismo modelo que resumen.py (2.0-flash quedó deprecado)
            contents=prompt,
        )
        return resp.text.strip()
    except Exception as e:
        return f"No pude consultar a Gemini ({e}). " + _respuesta_local(pregunta, df)
