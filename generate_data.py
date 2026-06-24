from faker import Faker
import random
import pandas as pd

fake = Faker()

data = []

for _ in range(500):
    data.append({
        "student_id": f"22A91A{random.randint(1000,9999)}",
        "student_name": fake.name(),
        "branch": random.choice(["CSE", "CSE-AI", "IT", "ECE"]),
        "company": random.choice([
            "Amazon",
            "Microsoft",
            "Deloitte",
            "TCS",
            "Accenture",
            "LSEG"
        ]),
        "stipend": random.choice([25000, 30000, 50000, None]),
        "fte_package": random.choice([3.36, 4.5, 7.6, 12, 18, 24]),
        "month_placed": random.choice(["Sep", "Oct", "Nov", "Dec"])
    })

df = pd.DataFrame(data)

df.to_csv("synthetic_placements.csv", index=False)

print(df.head())
print("\nCreated synthetic_placements.csv with", len(df), "rows")