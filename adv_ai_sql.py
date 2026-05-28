import ollama
import pyodbc
import sqlparse
import re

from tabulate import tabulate

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;"
    "DATABASE=Northwind;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

cursor = conn.cursor()
embedding = OllamaEmbeddings(
    model="nomic-embed-text"
)

vectordb = Chroma(
    persist_directory="./chroma_db",
    embedding_function=embedding
)

while True:

    question = input("\nAsk Question: ")

    if question.lower() == "exit":
        break

    docs = vectordb.similarity_search(
        question,
        k=5
    )

    schema_context = "\n".join(
        [doc.page_content for doc in docs]
    )
    prompt = f"""
STRICT RULES:
- ONLY generate valid SQL Server syntax
- NEVER use LIMIT
- SQL Server uses TOP
- NEVER invent columns
- ONLY use columns from schema
- Output ONLY raw SQL
- No explanation
- No markdown
- No comments
- ONLY SELECT queries
- Return ALL matching rows unless user explicitly asks for TOP or LIMIT
- Use exact requested columns

Correct Example:
SELECT TOP 1 Country
FROM Customers
GROUP BY Country
ORDER BY COUNT(CustomerID) DESC

Database Schema:
{schema_context}

User Question:
{question}
"""

    response = ollama.chat(
        model='llama3.2',
        messages=[
            {
                'role': 'user',
                'content': prompt
            }
        ]
    )

    sql_query = response['message']['content']
    sql_query = sql_query.replace("```sql", "")
    sql_query = sql_query.replace("```", "")
    sql_query = sql_query.strip()

    sql_query = sql_query.replace(
        "LIMIT TOP",
        "TOP"
    )

    if "LIMIT" in sql_query.upper():

        match = re.search(
            r'LIMIT\s+(\d+)',
            sql_query,
            re.IGNORECASE
        )

        if match:

            limit_num = match.group(1)

            sql_query = re.sub(
                r'LIMIT\s+\d+',
                '',
                sql_query,
                flags=re.IGNORECASE
            )

            sql_query = sql_query.replace(
                "SELECT",
                f"SELECT TOP {limit_num}",
                1
            )

    print("\nGenerated SQL:\n")
    print(sql_query)

    parsed = sqlparse.parse(sql_query)

    if not parsed:
        print("Invalid SQL")
        continue

    forbidden = [
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "TRUNCATE"
    ]

    if any(word in sql_query.upper() for word in forbidden):
        print("Dangerous query blocked.")
        continue

    try:

        cursor.execute(sql_query)

        rows = cursor.fetchall()

        columns = [
            column[0]
            for column in cursor.description
        ]

        results_list = []

        for row in rows:

            row_dict = dict(zip(columns, row))


            results_list.append(row_dict)

        print("\nResults Table:\n")

        print(
            tabulate(
                results_list,
                headers="keys",
                tablefmt="grid"
            )
        )

        summary_prompt = f"""
You are an AI analytics assistant.
Generate ONLY 1-2 short lines explaining the result.
Rules:
- Be concise
- No extra analysis
- No recommendations
- No long explanations
- Sound like dashboard insight text
- Mention key result directly

User Question:
{question}

SQL Results:
{results_list}

Examples:

Input:
[{{'Country': 'USA'}}]

Output:
USA has the highest number of customers.

Input:
[{{'Month': 'April', 'SalesPerMonth': 105}}]

Output:
April recorded the highest sales with 105 orders.

Now generate insight for:

{results_list}
"""

        summary_response = ollama.chat(
            model='llama3.2',
            messages=[
                {
                    'role': 'user',
                    'content': summary_prompt
                }
            ]
        )

        summary = summary_response['message']['content']

        print("\n" + "=" * 50)
        print("AI INSIGHT")
        print("=" * 50)

        print("\n" + summary)

    except Exception as e:

        print("\nExecution Error:")
        print(e)
