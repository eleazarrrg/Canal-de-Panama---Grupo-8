"""Resumen ejecutivo con LLM (Gemini) + degradación a plantilla local.

Diseño desacoplado del proveedor: la función pública es `generar_resumen(stats)`.
Para cambiar de proveedor, basta reemplazar `_resumen_gemini` por otro backend
con la misma firma. Si no hay API key (o la llamada falla), se usa una plantilla
local con las MISMAS cifras, para que la app nunca se caiga.
"""
from __future__ import annotations

MODELO_LLM = "gemini-flash-latest"  # alias al último flash estable (evita deprecación)

PROMPT = """Eres analista del Canal de Panamá. Con estos datos escribe un resumen
ejecutivo de 3 párrafos para directivos, en español y con tono profesional.
No inventes cifras: usa solo las que se dan. Relaciona la disponibilidad de agua
(lluvia/Lago Gatún) con la capacidad de tránsito.

- Tránsitos último mes: {transitos}
- Variación vs. año anterior: {variacion}
- Nivel del Lago Gatún: {nivel} m
- Lluvia acumulada 12 meses: {lluvia_acum} mm
- Pronóstico próximos 3 meses: {pronostico}
"""


def generar_resumen(stats: dict, api_key: str | None = None) -> str:
    """Devuelve el resumen ejecutivo. Usa Gemini si hay api_key; si no, plantilla."""
    if api_key:
        try:
            return _resumen_gemini(stats, api_key)
        except Exception:
            pass  # ante cualquier fallo de la API, degrada a plantilla
    return _resumen_plantilla(stats)


def _resumen_gemini(stats: dict, api_key: str) -> str:
    # SDK nuevo de Google (google-genai); reemplaza al deprecado google-generativeai.
    from google import genai

    cliente = genai.Client(api_key=api_key)
    respuesta = cliente.models.generate_content(model=MODELO_LLM, contents=PROMPT.format(**stats))
    return respuesta.text.strip()


def _resumen_plantilla(stats: dict) -> str:
    return (
        f"En el último mes registrado, el Canal de Panamá totalizó "
        f"{stats['transitos']} tránsitos, una variación de {stats['variacion']} "
        f"frente al mismo mes del año anterior. El nivel del Lago Gatún se ubicó "
        f"en {stats['nivel']} m.\n\n"
        f"La disponibilidad de agua, medida como la lluvia acumulada de 12 meses "
        f"({stats['lluvia_acum']} mm), es el factor que condiciona la capacidad "
        f"operativa del Canal: cuando el agua escasea, la ACP reduce los cupos "
        f"diarios y, con ellos, los tránsitos, como ocurrió durante la sequía de "
        f"2023–2024.\n\n"
        f"Para los próximos tres meses, el modelo proyecta {stats['pronostico']}. "
        f"Estas cifras son estimaciones y deben interpretarse junto con su "
        f"intervalo de confianza."
    )


if __name__ == "__main__":
    demo = {
        "transitos": "1,106", "variacion": "-3.0%", "nivel": "26.69",
        "lluvia_acum": "2867", "pronostico": "un promedio de ~1,120 tránsitos/mes",
    }
    print(generar_resumen(demo))  # sin key -> plantilla
