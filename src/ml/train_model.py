"""Entrenamiento y evaluación del modelo de tránsitos (RandomForest).

- Split TEMPORAL: los últimos 12 meses (FY2025) como test, no aleatorio.
- Métricas: MAE, RMSE, R² + baselines (persistencia y estacional) para
  contextualizar.
- Importancia de variables: se reporta TAL CUAL sale. No se manipula el set de
  features para inflar el aporte de la lluvia (la tesis se sostiene con el
  análisis bivariado + mecanismo, no con el ranking del RF).

Guarda: models/modelo.pkl, models/metricas.json, models/importancia.csv
"""
from __future__ import annotations

import json
import pathlib
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.ml.features import FEATURES, TARGET, construir_features

DATOS = ROOT / "data" / "processed" / "canal.parquet"
MODELO = ROOT / "models" / "modelo.pkl"
METRICAS = ROOT / "models" / "metricas.json"
IMPORTANCIA = ROOT / "models" / "importancia.csv"
N_TEST = 12  # últimos 12 meses = FY2025


def entrenar() -> dict:
    df = pd.read_parquet(DATOS)
    feat = construir_features(df)
    X, y, fechas = feat[FEATURES], feat[TARGET], feat["fecha"]

    # Split temporal (sin barajar): entrena con el pasado, evalúa el último año.
    Xtr, Xte = X.iloc[:-N_TEST], X.iloc[-N_TEST:]
    ytr, yte = y.iloc[:-N_TEST], y.iloc[-N_TEST:]

    modelo = RandomForestRegressor(n_estimators=400, random_state=42, n_jobs=-1)
    modelo.fit(Xtr, ytr)
    pred = modelo.predict(Xte)

    mae = mean_absolute_error(yte, pred)
    rmse = float(np.sqrt(mean_squared_error(yte, pred)))
    r2 = r2_score(yte, pred)

    # Baselines ingenuos para contextualizar el MAE.
    mae_persistencia = mean_absolute_error(yte, Xte["transitos_lag1"])
    mae_estacional = mean_absolute_error(yte, Xte["transitos_lag12"])

    imp = (
        pd.DataFrame({"feature": FEATURES, "importancia": modelo.feature_importances_})
        .sort_values("importancia", ascending=False)
        .reset_index(drop=True)
    )

    MODELO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, MODELO)
    imp.to_csv(IMPORTANCIA, index=False)

    metricas = {
        "modelo": "RandomForestRegressor(n_estimators=400)",
        "features": FEATURES,
        "target": TARGET,
        "evaluacion": "one-step-ahead (rezagos reales) sobre el test temporal",
        "split": {
            "train_meses": len(Xtr),
            "test_meses": len(Xte),
            "test_desde": str(fechas.iloc[-N_TEST].date()),
            "test_hasta": str(fechas.iloc[-1].date()),
        },
        "MAE": round(mae, 2),
        "RMSE": round(rmse, 2),
        "R2": round(r2, 4),
        "baselines_MAE": {
            "persistencia_lag1": round(mae_persistencia, 2),
            "estacional_lag12": round(mae_estacional, 2),
        },
        "importancia": imp.set_index("feature")["importancia"].round(4).to_dict(),
    }
    METRICAS.write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8")

    # Adjunta detalle para impresión (no se serializa).
    metricas["_detalle"] = pd.DataFrame(
        {
            "fecha": fechas.iloc[-N_TEST:].dt.date.values,
            "real": yte.values,
            "pred": pred.round().astype(int),
        }
    )
    metricas["_detalle"]["error"] = metricas["_detalle"]["pred"] - metricas["_detalle"]["real"]
    metricas["_importancia"] = imp
    return metricas


if __name__ == "__main__":
    m = entrenar()
    print("== Modelo:", m["modelo"])
    print("Features:", m["features"])
    print(
        f"Train: {m['split']['train_meses']} meses | "
        f"Test: {m['split']['test_meses']} meses "
        f"({m['split']['test_desde']} -> {m['split']['test_hasta']})"
    )
    print(f"\nMAE  = {m['MAE']}  tránsitos/mes")
    print(f"RMSE = {m['RMSE']}")
    print(f"R2   = {m['R2']}")
    print("\nBaselines (MAE):")
    print(f"  persistencia (lag1) = {m['baselines_MAE']['persistencia_lag1']}")
    print(f"  estacional  (lag12) = {m['baselines_MAE']['estacional_lag12']}")
    print("\nImportancia de variables (tal cual sale):")
    print(m["_importancia"].to_string(index=False))
    print("\nReal vs Predicho (test, one-step-ahead):")
    print(m["_detalle"].to_string(index=False))
