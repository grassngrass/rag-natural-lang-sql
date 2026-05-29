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
import json
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
with open(
    "relationship_graph.json",
    "r"
) as f:

    relationship_graph = json.load(f)

while True:

    question = input("\nAsk Question: ")

    if question.lower() == "exit":
        break

    question_lower = question.lower()
    # Detect ID filters
    id_hint = ""

    id_match = re.search(
        r'(\w+)\s*id\s*(\d+)',
        question,
        re.IGNORECASE
    )

    if id_match:

        id_hint = """
IMPORTANT:
The user specified a specific ID value.
Use a WHERE clause.
Do NOT return all rows.

Examples:

OrderID 10248
-> WHERE OrderID = 10248

ProductID 11
-> WHERE ProductID = 11

EmployeeID 5
-> WHERE EmployeeID = 5
"""

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
        k=15
    )

    schema_context = "\n".join(
        [doc.page_content for doc in docs]
    )

    # BUILD RELATIONSHIP CONTEXT
    join_context = ""

    for table_name, joins in relationship_graph.items():

        for join in joins:

            join_context += (
                f"{table_name}.{join['column']} "
                f"joins "
                f"{join['ref_table']}."
                f"{join['ref_column']}\n"
            )

    prompt = f"""
You are an expert SQL Server query generator.

RULES:

1. Use ONLY SQL Server syntax.
2. Use ONLY tables from schema.
3. Use ONLY columns from schema.
4. Never invent tables.
5. Never invent columns.
6. Use JOINs only when needed.
7. Follow provided relationships.
8. Return ONLY SQL.
9. No markdown.
10. No explanation.
11. SELECT queries only.
STRICT RULES:
- ONLY generate valid SQL Server syntax
- NEVER invent columns
- ONLY use schema columns
IMPORTANT:

When columns belong to different tables,
find a join path using the relationship graph.

Example:
Orders.ShipVia joins Shippers.ShipperID

To get OrderID and CompanyName:

SELECT O.OrderID, S.CompanyName
FROM Orders O
JOIN Shippers S
ON O.ShipVia = S.ShipperID

IMPORTANT:

If the user specifies an ID value
(OrderID, ProductID, CustomerID, EmployeeID, etc.)

ALWAYS include a WHERE clause.

Examples:

User:
What is the shipper company name for Order ID 10248?

SQL:
SELECT S.CompanyName
FROM Orders O
JOIN Shippers S
ON O.ShipVia = S.ShipperID
WHERE O.OrderID = 10248

User:
What is the product name for ProductID 11?

SQL:
SELECT ProductName
FROM Products
WHERE ProductID = 11

IMPORTANT TABLE RULES:

- ProductID belongs to [Order Details] and Products tables.
- Orders table does NOT contain ProductID.
- If a question contains both OrderID and ProductID,
  use [Order Details].
Products.SupplierID joins Suppliers.SupplierID.

To find supplier information for a product:

SELECT S.SupplierID, S.CompanyName
FROM Products P
JOIN Suppliers S
ON P.SupplierID = S.SupplierID

ProductID belongs to Products.
SupplierID belongs to Suppliers.

Never use:
- BusinessEntityID
- EmployeeTerritories
- Orders

when answering supplier-for-product questions.

Examples:

Question:
What is the ProductID for OrderID 10248?

SQL:
SELECT ProductID
FROM [Order Details]
WHERE OrderID = 10248

Question:
What products were ordered in OrderID 10248?

SQL:
SELECT ProductID
FROM [Order Details]
WHERE OrderID = 10248

Database Schema:
{schema_context}

Relationships:
{join_context}

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
        # skip this iteration of the main input loop
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

        error_message = str(e)

        retry_prompt = f"""
The SQL query failed.

Error:
{error_message}

Original SQL:
{sql_query}

Schema:
{schema_context}

Relationships:
{join_context}

Generate corrected SQL only.
"""

        retry_response = ollama.chat(
            model="llama3.2",
            messages=[
                {
                    "role": "user",
                    "content": retry_prompt
                }
            ]
        )

        corrected_sql = (
            retry_response["message"]["content"]
            .replace("```sql", "")
            .replace("```", "")
            .strip()
        )

        print("\nCorrected SQL:")
        print(corrected_sql)

        retry_prompt = f"""
You are a SQL Server query fixer.

RULES:
- Return ONLY SQL.
- No explanation.
- No markdown.
- No comments.
- No English text.
- One SQL query only.

Database Schema:
{schema_context}

Relationships:
{join_context}

Failed SQL:
{sql_query}

Error:
{error_message}

Generate corrected SQL only.
"""

        retry_response = ollama.chat(
            model="llama3.2",
            messages=[
                {
                    "role": "user",
                    "content": retry_prompt
                }
            ]
        )

        corrected_sql = (
            retry_response["message"]["content"]
            .replace("```sql", "")
            .replace("```", "")
            .strip()
        )

        import re

        match = re.search(
            r"(SELECT[\s\S]*)",
            corrected_sql,
            re.IGNORECASE
        )

        if match:
            corrected_sql = match.group(1).strip()

        print("\nCorrected SQL:")
        print(corrected_sql)
