from groq import Groq
import os

client = Groq(
    api_key=os.environ.get("GROQ_API_KEY")
)

question = input("Ask: ")

prompt = f"""
You are a PostgreSQL expert.

Table schema:

placements(
    student_id,
    student_name,
    branch,
    company,
    stipend,
    fte_package,
    month_placed
)

Convert the question into SQL.

Return ONLY SQL.

Question:
{question}
"""

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {
            "role": "user",
            "content": prompt
        }
    ]
)

print(response.choices[0].message.content)