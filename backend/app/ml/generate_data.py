"""Generate simulated loan application data for credit risk model training."""

import numpy as np
import pandas as pd
from pathlib import Path


def generate_credit_data(n_samples: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    age = rng.integers(21, 66, size=n_samples)
    gender = rng.choice(["Male", "Female"], size=n_samples)
    income = rng.integers(20000, 200001, size=n_samples)
    education = rng.choice(["Graduate", "Not Graduate"], size=n_samples, p=[0.55, 0.45])
    marital_status = rng.choice(["Married", "Single"], size=n_samples, p=[0.6, 0.4])
    employment_years = rng.integers(0, 31, size=n_samples)
    loan_amount = rng.integers(5000, 500001, size=n_samples)
    loan_term = rng.choice([12, 24, 36, 48, 60], size=n_samples)
    credit_score = rng.integers(300, 851, size=n_samples)
    existing_loans = rng.integers(0, 6, size=n_samples)
    property_type = rng.choice(["Own", "Rent", "None"], size=n_samples, p=[0.4, 0.4, 0.2])
    monthly_debt = rng.integers(0, 5001, size=n_samples)

    df = pd.DataFrame({
        "Age": age,
        "Gender": gender,
        "Income": income,
        "Education": education,
        "Marital_Status": marital_status,
        "Employment_Years": employment_years,
        "Loan_Amount": loan_amount,
        "Loan_Term": loan_term,
        "Credit_Score": credit_score,
        "Existing_Loans": existing_loans,
        "Property_Type": property_type,
        "Monthly_Debt": monthly_debt,
    })

    # Derive helper ratios for labelling
    dti = (monthly_debt * 12) / np.maximum(income, 1)  # debt-to-income ratio
    lti = loan_amount / np.maximum(income, 1)           # loan-to-income ratio

    # Score: higher is better credit
    score = np.zeros(n_samples, dtype=float)
    score += np.clip((credit_score - 300) / 550, 0, 1) * 40        # 0-40 from credit score
    score += np.clip(income / 200000, 0, 1) * 15                   # 0-15 from income
    score += np.clip(employment_years / 30, 0, 1) * 10             # 0-10 from employment
    score -= np.clip(dti, 0, 1) * 10                                # penalty for high dti
    score -= np.clip(lti, 0, 5) * 4                                 # penalty for high lti
    score -= existing_loans * 2                                      # penalty for existing loans
    score += np.where(np.array(education) == "Graduate", 5, 0)     # bonus for education
    score += np.where(np.array(property_type) == "Own", 5, 0)      # bonus for property ownership

    # Add noise
    score += rng.normal(0, 3, size=n_samples)

    # Map score to P1-P4
    labels = np.empty(n_samples, dtype=object)
    labels[score >= 50] = "P1"
    labels[(score >= 35) & (score < 50)] = "P2"
    labels[(score >= 20) & (score < 35)] = "P3"
    labels[score < 20] = "P4"

    df["Approved_Flag"] = labels
    return df


if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / "sample_credit_data.csv"

    df = generate_credit_data()
    df.to_csv(output_path, index=False)
    print(f"Generated {len(df)} records -> {output_path}")
    print(f"Label distribution:\n{df['Approved_Flag'].value_counts().sort_index()}")
