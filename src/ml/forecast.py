"""Pronóstico recursivo de tránsitos para FY2026 (oct-2025 .. sep-2026).

- Usa el modelo entrenado en models/modelo.pkl.
- Regresor de lluvia: REAL desde data/raw/clima.csv hasta may-2026; climatología
  (media mensual histórica) para jun-sep 2026.
- Recursivo: solo `transitos_lag1` se realimenta con las predicciones.
  `transitos_lag12` y la lluvia acumulada son conocidos (no se inventan).
- Banda de confianza: ±1.96 · RMSE de un BACKTEST RECURSIVO sobre FY2025
  (entrenando solo hasta sep-2024), que refleja el error multi-paso real.

Escribe models/pronostico.csv y models/pronostico.json.
"""
from __future__ import annotations

import json
import pathlib
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.ml.features import FEATURES, TARGET, construir_features

PARQUET = ROOT / "data" / "processed" / "canal.parquet"
CLIMA = ROOT / "data" / "raw" / "clima.csv"
MODELO = ROOT / "models" / "modelo.pkl"
PRONOSTICO = ROOT / "models" / "pronostico.csv"
META = ROOT / "models" / "pronostico.json"

HORIZONTE_FIN = "2026-09-01"  # fin del año fiscal 2026
Z = 1.96


def _lluvia_futura(fut: pd.DatetimeIndex):
    """lluvia_mm mensual para las fechas futuras: real (clima.csv) + climatología."""
    diario = pd.read_csv(CLIMA, parse_dates=["fecha"])
    men = diario.set_index("fecha")["precipitation_sum"].resample("MS").sum()
    men.index = men.index.normalize()
    climatologia = men.groupby(men.index.month).mean()  # media por mes calendario

    lluvia, fuente = [], []
    for f in fut:
        f = pd.Timestamp(f)
        if f in men.index:
            lluvia.append(float(men.loc[f]))
            fuente.append("real")
        else:
            lluvia.append(float(climatologia.loc[f.month]))
            fuente.append("climatologia")
    return lluvia, fuente


def _recursar(modelo, full: pd.DataFrame, fechas_pred) -> dict:
    """Predice recursivamente realimentando solo `transitos_lag1`.

    `full` debe tener columnas fecha, mes, lluvia_mm, lluvia_acum_12m,
    transitos_total (NaN en las fechas a predecir), con índice 0..n contiguo.
    """
    trans = full["transitos_total"].to_numpy(dtype=float).copy()
    pos = {f: i for i, f in enumerate(full["fecha"])}
    preds = {}
    for f in fechas_pred:
        i = pos[pd.Timestamp(f)]
        x = pd.DataFrame([{
            "mes": full.at[i, "mes"],
            "lluvia_mm": full.at[i, "lluvia_mm"],
            "lluvia_acum_12m": full.at[i, "lluvia_acum_12m"],
            "transitos_lag1": trans[i - 1],
            "transitos_lag12": trans[i - 12],
        }])[FEATURES]
        yhat = float(modelo.predict(x)[0])
        trans[i] = yhat  # realimenta para el lag1 del mes siguiente
        preds[pd.Timestamp(f)] = yhat
    return preds


def _rmse_backtest() -> float:
    """RMSE de un pronóstico recursivo de FY2025 entrenando solo hasta sep-2024."""
    df = pd.read_parquet(PARQUET).sort_values("fecha").reset_index(drop=True)
    df["mes"] = df["fecha"].dt.month
    df["lluvia_acum_12m"] = df["lluvia_mm"].rolling(12).sum()

    feat = construir_features(df)
    train = feat[feat["fecha"] < "2024-10-01"]
    modelo = RandomForestRegressor(n_estimators=400, random_state=42, n_jobs=-1)
    modelo.fit(train[FEATURES], train[TARGET])

    fy25 = pd.date_range("2024-10-01", "2025-09-01", freq="MS")
    full = df.copy()
    full.loc[full["fecha"].isin(fy25), "transitos_total"] = np.nan
    preds = _recursar(modelo, full, list(fy25))

    real = df.set_index("fecha")["transitos_total"]
    err = np.array([preds[f] - real[f] for f in fy25])
    return float(np.sqrt((err ** 2).mean()))


def generar_pronostico() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET).sort_values("fecha").reset_index(drop=True)
    modelo = joblib.load(MODELO)

    fut = pd.date_range("2025-10-01", HORIZONTE_FIN, freq="MS")
    lluvia_fut, fuente_fut = _lluvia_futura(fut)

    hist = df[["fecha", "lluvia_mm", "transitos_total"]].copy()
    futrows = pd.DataFrame({"fecha": fut, "lluvia_mm": lluvia_fut, "transitos_total": np.nan})
    full = pd.concat([hist, futrows], ignore_index=True)
    full["mes"] = full["fecha"].dt.month
    full["lluvia_acum_12m"] = full["lluvia_mm"].rolling(12).sum()

    preds = _recursar(modelo, full, list(fut))
    serie = np.array([preds[f] for f in fut])
    rmse = _rmse_backtest()
    banda = Z * rmse

    out = pd.DataFrame({
        "fecha": fut,
        "pred": np.round(serie).astype(int),
        "lo": np.round(serie - banda).astype(int),
        "hi": np.round(serie + banda).astype(int),
        "lluvia_fuente": fuente_fut,
    })
    out.to_csv(PRONOSTICO, index=False)
    META.write_text(json.dumps({
        "horizonte": "FY2026 (oct-2025 a sep-2026)",
        "rmse_recursivo_fy2025": round(rmse, 2),
        "z": Z,
        "banda": "pred ± 1.96 · RMSE recursivo (backtest FY2025)",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    fc = generar_pronostico()
    meta = json.loads(META.read_text(encoding="utf-8"))
    print("RMSE recursivo (backtest FY2025):", meta["rmse_recursivo_fy2025"])
    print("\nPronóstico FY2026:")
    print(fc.to_string(index=False))
    parc = fc[fc["fecha"] <= "2026-05-01"]["pred"].sum()
    print(f"\nChequeo out-of-sample: acumulado pronóstico oct25-may26 (total) = {parc:,}")
    print("ACP real oct25-may26 = 8,593 (base alto calado, métrica distinta, solo referencia)")
