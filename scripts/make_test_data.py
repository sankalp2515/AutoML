"""Generate deterministic test CSVs for QA — standard library only (no installs).

Run from anywhere with any Python 3:
    python scripts/make_test_data.py
Writes CSVs into ./test_data/ . Each file is small and has clear column names so a
tester can pick a sensible goal. Seeded, so every run produces identical files.
"""

import csv
import os
import random

random.seed(42)
OUT = os.path.join(os.path.dirname(__file__), "..", "test_data")
os.makedirs(OUT, exist_ok=True)


def write(name, header, rows):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {path}  ({len(rows)} rows)")


# 1. iris-like 3-class classification (150 rows) — for "honest holdout" + multiclass
def iris():
    rows = []
    centers = {"setosa": (5.0, 3.4, 1.5, 0.2), "versicolor": (5.9, 2.8, 4.3, 1.3),
               "virginica": (6.6, 3.0, 5.6, 2.0)}
    for species, (a, b, c, d) in centers.items():
        for _ in range(50):
            rows.append([round(a + random.gauss(0, 0.35), 2), round(b + random.gauss(0, 0.3), 2),
                         round(c + random.gauss(0, 0.4), 2), round(d + random.gauss(0, 0.2), 2), species])
    random.shuffle(rows)
    write("iris.csv", ["sepal_length", "sepal_width", "petal_length", "petal_width", "species"], rows)


# 2. binary churn (200 rows) — for binary classification + deploy/predict
def churn():
    rows = []
    for _ in range(200):
        tenure = random.randint(1, 72)
        monthly = round(random.uniform(20, 120), 2)
        contract = random.choice(["month-to-month", "one-year", "two-year"])
        # churn more likely with short tenure + month-to-month
        p = 0.6 if (tenure < 12 and contract == "month-to-month") else 0.15
        rows.append([tenure, monthly, round(monthly * tenure, 2), contract, int(random.random() < p)])
    write("churn.csv", ["tenure", "monthly_charges", "total_charges", "contract_type", "churned"], rows)


# 3. regression (200 rows) — for regression task + RMSE
def house():
    rows = []
    for _ in range(200):
        area = random.randint(500, 3500)
        beds = random.randint(1, 6)
        age = random.randint(0, 80)
        dist = round(random.uniform(0.5, 30), 1)
        price = round(area * 180 + beds * 15000 - age * 800 - dist * 3000 + random.gauss(0, 15000), 2)
        rows.append([area, beds, age, dist, price])
    write("house.csv", ["area_sqft", "bedrooms", "age_years", "distance_km", "price"], rows)


# 4. imbalanced fraud (~2% positive, 500 rows) — for "fraud -> recall/pr_auc" framing
def fraud():
    rows = []
    for _ in range(500):
        is_fraud = int(random.random() < 0.02)
        amount = round(random.uniform(500, 5000) if is_fraud else random.uniform(1, 300), 2)
        rows.append([amount, random.randint(1, 20), random.randint(1, 3000), is_fraud])
    write("fraud.csv", ["amount", "n_txn_today", "account_age_days", "is_fraud"], rows)


# 5. tiny dataset (40 rows) — for the small-data holdout FALLBACK test (<60 rows)
def tiny():
    rows = [[round(random.gauss(0, 1), 3), round(random.gauss(0, 1), 3),
             int(random.random() < 0.5)] for _ in range(40)]
    write("tiny.csv", ["feature_a", "feature_b", "label"], rows)


if __name__ == "__main__":
    iris(); churn(); house(); fraud(); tiny()
    print("\nDone. Upload these from the test_data/ folder during QA.")
