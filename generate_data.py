from faker import Faker
import random
import pandas as pd

fake = Faker()

# Company universe must match documents/ exactly (one .txt per company below)
# so the SQL branch and RAG branch never disagree about which companies exist.
# fte_package_range/stipend_range are company-specific so SQL answers stay
# internally plausible (e.g. Google/Goldman Sachs pay more than Wipro/Cognizant),
# matching the qualitative claims made in each company's eligibility doc.
COMPANIES = {
    "Amazon":        {"package_range": (12, 24),   "stipend_range": (50000, 90000)},
    "Microsoft":     {"package_range": (12, 24),   "stipend_range": (50000, 90000)},
    "Google":        {"package_range": (18, 40),   "stipend_range": (80000, 120000)},
    "Goldman Sachs":  {"package_range": (15, 28),   "stipend_range": (70000, 100000)},
    "Adobe":         {"package_range": (14, 26),   "stipend_range": (60000, 90000)},
    "Salesforce":    {"package_range": (10, 20),   "stipend_range": (40000, 70000)},
    "LSEG":          {"package_range": (10, 18),   "stipend_range": (40000, 60000)},
    "Deloitte":      {"package_range": (4.5, 8),   "stipend_range": (20000, 35000)},
    "Accenture":     {"package_range": (4.0, 7.5), "stipend_range": (18000, 30000)},
    "TCS":           {"package_range": (3.36, 9),  "stipend_range": (15000, 25000)},
    "Cognizant":     {"package_range": (3.6, 8),   "stipend_range": (15000, 25000)},
    "Wipro":         {"package_range": (3.5, 6.5), "stipend_range": (15000, 22000)},
}

data = []

for _ in range(600):
    company = random.choice(list(COMPANIES.keys()))
    pkg_lo, pkg_hi = COMPANIES[company]["package_range"]
    stipend_lo, stipend_hi = COMPANIES[company]["stipend_range"]

    data.append({
        "student_id": f"22A91A{random.randint(1000,9999)}",
        "student_name": fake.name(),
        "branch": random.choice(["CSE", "CSE-AI", "IT", "ECE"]),
        "company": company,
        "stipend": random.choice([round(random.uniform(stipend_lo, stipend_hi), -3), None]),
        "fte_package": round(random.uniform(pkg_lo, pkg_hi), 2),
        "month_placed": random.choice(["Sep", "Oct", "Nov", "Dec"])
    })

df = pd.DataFrame(data)

df.to_csv("synthetic_placements.csv", index=False)

print(df.head())
print("\nCreated synthetic_placements.csv with", len(df), "rows across", len(COMPANIES), "companies")