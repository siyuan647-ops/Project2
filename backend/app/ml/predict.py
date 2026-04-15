"""Load trained model and perform batch credit risk prediction."""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent / "model"

CATEGORICAL_COLS = ["Gender", "Education", "Marital_Status", "Property_Type"]
NUMERICAL_COLS = [
    "Age", "Income", "Employment_Years", "Loan_Amount",
    "Loan_Term", "Credit_Score", "Existing_Loans", "Monthly_Debt",
]
LABEL_ORDER = ["P1", "P2", "P3", "P4"]


@dataclass
class PredictionResult:
    df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


class CreditPredictor:
    def __init__(self):
        self.model = None
        self.label_encoders = None
        self.scaler = None
        self.meta = None

    def load(self):
        self.model = joblib.load(MODEL_DIR / "xgboost_credit.pkl")
        self.label_encoders = joblib.load(MODEL_DIR / "label_encoders.pkl")
        self.scaler = joblib.load(MODEL_DIR / "scaler.pkl")
        with open(MODEL_DIR / "meta.json") as f:
            self.meta = json.load(f)

    def predict(self, df: pd.DataFrame) -> PredictionResult:
        if self.model is None:
            self.load()

        df = df.copy()
        warnings: list[str] = []

        # Feature engineering
        df["DTI"] = (df["Monthly_Debt"] * 12) / df["Income"].clip(lower=1)
        df["LTI"] = df["Loan_Amount"] / df["Income"].clip(lower=1)

        # Encode categoricals with case-insensitive matching
        for col in CATEGORICAL_COLS:
            le = self.label_encoders[col]
            # Build case-insensitive lookup: lowercase -> original class name
            ci_lookup: dict[str, str] = {c.lower(): c for c in le.classes_}

            def _normalise(val: str) -> str | None:
                v = val.strip()
                if v in le.classes_:
                    return v
                lowered = v.lower()
                if lowered in ci_lookup:
                    return ci_lookup[lowered]
                return None

            raw_values = df[col].astype(str)
            normalised = raw_values.apply(_normalise)

            # Collect rows with truly unknown values
            unknown_mask = normalised.isna()
            if unknown_mask.any():
                unknown_rows = df.index[unknown_mask].tolist()
                unknown_vals = raw_values[unknown_mask].unique().tolist()
                valid_options = ", ".join(le.classes_)
                for uv in unknown_vals:
                    row_indices = df.index[raw_values == uv].tolist()
                    row_display = row_indices[:5]
                    suffix = f" 等共 {len(row_indices)} 行" if len(row_indices) > 5 else ""
                    warnings.append(
                        f"列 '{col}' 中出现未知值 '{uv}'（第 {', '.join(str(r + 2) for r in row_display)}{suffix} 行），"
                        f"已替换为默认值 '{le.classes_[0]}'。合法值: [{valid_options}]"
                    )
                normalised = normalised.fillna(le.classes_[0])

            # Check if case was auto-corrected
            corrected_mask = (raw_values != normalised) & ~unknown_mask
            if corrected_mask.any():
                corrected_pairs: dict[str, str] = {}
                for orig, normed in zip(raw_values[corrected_mask], normalised[corrected_mask]):
                    if orig not in corrected_pairs:
                        corrected_pairs[orig] = normed
                for orig, normed in corrected_pairs.items():
                    warnings.append(
                        f"列 '{col}' 中 '{orig}' 已自动修正为 '{normed}'（大小写规范化）"
                    )

            df[col] = le.transform(normalised)

        feature_cols = self.meta["feature_cols"]
        num_cols_to_scale = self.meta["num_cols_to_scale"]

        X = df[feature_cols].copy()
        X[num_cols_to_scale] = self.scaler.transform(X[num_cols_to_scale])

        preds = self.model.predict(X)
        df["Approved_Flag"] = [LABEL_ORDER[int(p)] for p in preds]
        return PredictionResult(df=df, warnings=warnings)


# Module-level singleton
_predictor = CreditPredictor()


def predict_credit_risk(df: pd.DataFrame) -> PredictionResult:
    return _predictor.predict(df)
