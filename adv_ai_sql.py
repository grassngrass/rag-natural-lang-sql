try:
    import ollama
except ImportError:
    class _OllamaStub:
        @staticmethod
        def chat(*args, **kwargs):
            raise RuntimeError(
                "The 'ollama' package is not installed. Install it with pip and try again."
            )

    ollama = _OllamaStub()
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

    question_lower = question.lower()

    # ==================================
    # TABLE BOOSTING
    # ==================================

    search_query = question

    if "order" in question_lower:
        search_query += " Order Details Orders"

    if "product" in question_lower:
        search_query += " Products Order Details"

    if "supplier" in question_lower:
        search_query += " Suppliers"

    if "employee" in question_lower:
        search_query += " Employees"

    if "customer" in question_lower:
        search_query += " Customers"

    if "territory" in question_lower:
        search_query += " Territories"

    if "region" in question_lower:
        search_query += " Region"

    # ==================================
    # RAG SEARCH
    # ==================================

    docs = vectordb.similarity_search(
        search_query,
        k=10
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
- NEVER invent tables
- NEVER invent columns
- Use ONLY tables from schema context
- Return ALL matching rows unless TOP is requested
- Use exact requested columns
- Distinguish carefully between table names and column names
- Do not use table names as columns
- Do not perform JOINs unless columns from multiple tables are requested.
- If all requested columns exist in one table, query only that table.
- Verify join column data types are compatible.
- Use only actual columns from schema.
- EmployeeName is not a real column.
- For full employee names use:
  FirstName + ' ' + LastName AS EmployeeName
- Do not reference aliases in WHERE clauses.
IMPORTANT:
- Use exact table names from schema.
- Some table names contain spaces.
- Wrap table names containing spaces in square brackets.
- Example:
  [Order Details]
  [CustomerCustomerDemo]
  IMPORTANT TABLE RULES:

- ProductID + OrderID => use [Order Details]
- OrderID does NOT exist in Products
- ProductID exists in Products and [Order Details]
- Supplier questions => use Suppliers table
- Employee questions => use Employees table
- Territory questions => use Territories table
- Region questions => use Region table
COLUMN RELATIONSHIP RULES:

- If a question requires both OrderID and ProductID, use [Order Details].
- ProductID does not exist in Orders.
- OrderID does not exist in Products.
- [Order Details] contains both OrderID and ProductID.
- Before generating SQL, verify every requested column exists in the selected table.
JOIN RULES:

- Do NOT use JOIN unless columns from multiple tables are requested.
- If all requested columns exist in one table, query only that table.
- Country filters should use Country columns, not Region tables.
- Verify every column exists before generating SQL.

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
        "OrderDetails",
        "[Order Details]"
    )

    sql_query = sql_query.replace(
        "Order_Details",
        "[Order Details]"
    )

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
