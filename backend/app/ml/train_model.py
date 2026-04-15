"""Train an XGBoost multi-class model for credit risk prediction (P1-P4)."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import classification_report, accuracy_score
from xgboost import XGBClassifier


CATEGORICAL_COLS = ["Gender", "Education", "Marital_Status", "Property_Type"]
NUMERICAL_COLS = [
    "Age", "Income", "Employment_Years", "Loan_Amount",
    "Loan_Term", "Credit_Score", "Existing_Loans", "Monthly_Debt",
]
TARGET_COL = "Approved_Flag"
LABEL_ORDER = ["P1", "P2", "P3", "P4"]
  
MODEL_DIR = Path(__file__).resolve().parent / "model"   #模型/编码器/标准化器保存路径


def _feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived features."""
    df = df.copy()
    df["DTI"] = (df["Monthly_Debt"] * 12) / df["Income"].clip(lower=1)   #债务收入比（年度月债务 / 年收入）
    df["LTI"] = df["Loan_Amount"] / df["Income"].clip(lower=1)           #贷款收入比（贷款金额 / 年收入）
    return df
            

def train(data_path: str | Path | None = None):
    # Load data
    if data_path is None:
        data_path = Path(__file__).resolve().parent.parent.parent / "data" / "sample_credit_data.csv"
    df = pd.read_csv(data_path)

    # Feature engineering
    df = _feature_engineering(df)

    # Encode categorical features
    label_encoders: dict[str, LabelEncoder] = {}
    for col in CATEGORICAL_COLS:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))
        label_encoders[col] = le

    # Encode target
    target_le = LabelEncoder()
    target_le.classes_ = np.array(LABEL_ORDER)
    df[TARGET_COL] = target_le.transform(df[TARGET_COL])

    feature_cols = NUMERICAL_COLS + CATEGORICAL_COLS + ["DTI", "LTI"]
    X = df[feature_cols]
    y = df[TARGET_COL]

    # Scale numerical features
    scaler = StandardScaler()
    num_cols_to_scale = NUMERICAL_COLS + ["DTI", "LTI"]
    X[num_cols_to_scale] = scaler.fit_transform(X[num_cols_to_scale])

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Train
    model = XGBClassifier(
        objective="multi:softmax",
        num_class=4,
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        random_state=42,
        eval_metric="mlogloss",
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, target_names=LABEL_ORDER)
    print(f"Accuracy: {acc:.4f}")
    print(report)

    # Save artefacts
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_DIR / "xgboost_credit.pkl")
    joblib.dump(label_encoders, MODEL_DIR / "label_encoders.pkl")
    joblib.dump(scaler, MODEL_DIR / "scaler.pkl")

    # Save feature column order
    meta = {"feature_cols": feature_cols, "num_cols_to_scale": num_cols_to_scale}
    (MODEL_DIR / "meta.json").write_text(json.dumps(meta))

    print(f"\nArtifacts saved to {MODEL_DIR}")
    return model


if __name__ == "__main__":
    train()
