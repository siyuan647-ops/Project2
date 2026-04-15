"""Credit risk prediction API routes."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.ml.predict import predict_credit_risk
from app.schemas.models import CreditPredictionMeta

router = APIRouter()
limiter = Limiter(key_func=get_remote_address, config_filename=None)

REQUIRED_COLUMNS = [
    "Age", "Gender", "Income", "Education", "Marital_Status",
    "Employment_Years", "Loan_Amount", "Loan_Term", "Credit_Score",
    "Existing_Loans", "Property_Type", "Monthly_Debt",
]


@router.post("/predict", response_model=CreditPredictionMeta)
@limiter.limit(settings.RATE_LIMIT_CREDIT)
async def predict(request: Request, file: UploadFile = File(...)):
    """Upload an Excel/CSV file of loan applicants, return predictions."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".csv"):
        raise HTTPException(status_code=400, detail="Only .xlsx and .csv files are supported.")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10 MB).")

    import io
    if ext == ".csv":
        df = pd.read_csv(io.BytesIO(contents))
    else:
        df = pd.read_excel(io.BytesIO(contents))

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file contains no data.")

    # Validate columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {missing}")

    # Predict
    prediction = predict_credit_risk(df)
    result_df = prediction.df

    # Save result
    out_name = f"credit_result_{uuid.uuid4().hex[:8]}.xlsx"
    out_path = settings.OUTPUT_DIR / out_name
    result_df.to_excel(out_path, index=False)

    distribution = result_df["Approved_Flag"].value_counts().to_dict()

    return CreditPredictionMeta(
        filename=out_name,
        total_records=len(result_df),
        distribution=distribution,
        warnings=prediction.warnings,
        model_version="xgboost-v1",
        prediction_timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/download/{filename}")
async def download_result(filename: str):
    """Download a prediction result file."""
    safe_name = Path(filename).name
    file_path = settings.OUTPUT_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/template")
async def download_template():
    """Download an Excel template with the required columns and sample data."""
    import io
    sample = pd.DataFrame({
        "Age": [30, 45],
        "Gender": ["Male", "Female"],
        "Income": [80000, 120000],
        "Education": ["Graduate", "Not Graduate"],
        "Marital_Status": ["Married", "Single"],
        "Employment_Years": [5, 15],
        "Loan_Amount": [200000, 50000],
        "Loan_Term": [36, 24],
        "Credit_Score": [720, 650],
        "Existing_Loans": [1, 0],
        "Property_Type": ["Own", "Rent"],
        "Monthly_Debt": [500, 300],
    })
    buf = io.BytesIO()
    sample.to_excel(buf, index=False)
    buf.seek(0)

    tmp_path = settings.OUTPUT_DIR / "credit_template.xlsx"
    tmp_path.write_bytes(buf.getvalue())

    return FileResponse(
        path=str(tmp_path),
        filename="credit_template.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
