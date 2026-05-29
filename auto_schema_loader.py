import pyodbc

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings


# ==========================================
# SQL SERVER CONNECTION
# ==========================================

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;"
    "DATABASE=Northwind;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

cursor = conn.cursor()


# ==========================================
# GET ALL TABLES
# ==========================================

cursor.execute("""
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME
""")

tables = cursor.fetchall()


# ==========================================
# GET ALL FOREIGN KEYS
# ==========================================

cursor.execute("""
SELECT
    tp.name AS ParentTable,
    cp.name AS ParentColumn,
    tr.name AS ReferencedTable,
    cr.name AS ReferencedColumn
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc
    ON fk.object_id = fkc.constraint_object_id
JOIN sys.tables tp
    ON fkc.parent_object_id = tp.object_id
JOIN sys.columns cp
    ON fkc.parent_object_id = cp.object_id
    AND fkc.parent_column_id = cp.column_id
JOIN sys.tables tr
    ON fkc.referenced_object_id = tr.object_id
JOIN sys.columns cr
    ON fkc.referenced_object_id = cr.object_id
    AND fkc.referenced_column_id = cr.column_id
""")

relationships = cursor.fetchall()

schema_docs = []


# ==========================================
# LOOP THROUGH TABLES
# ==========================================

for table in tables:

    table_name = table[0]

    print(f"Loading table: {table_name}")

    # ======================================
    # GET COLUMNS
    # ======================================

    cursor.execute(f"""
    SELECT COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = '{table_name}'
    ORDER BY ORDINAL_POSITION
    """)

    columns = cursor.fetchall()

    column_text = ""

    for column in columns:

        column_name = column[0]
        data_type = column[1]

        column_text += (
            f"- {column_name} ({data_type})\n"
        )

    # ======================================
    # RELATIONSHIPS
    # ======================================

    relationship_text = ""

    for rel in relationships:

        parent_table = rel[0]
        parent_column = rel[1]
        referenced_table = rel[2]
        referenced_column = rel[3]

        if parent_table == table_name:

            relationship_text += (
                f"- {parent_table}.{parent_column} "
                f"joins "
                f"{referenced_table}.{referenced_column}\n"
            )

    if relationship_text == "":
        relationship_text = "No foreign key relationships found."

    # ======================================
    # TABLE NAME HINTS
    # ======================================

    table_hint = ""

    if " " in table_name:

        table_hint = f"""
IMPORTANT:
This table name contains spaces.

Correct:
[{table_name}]

Wrong:
{table_name.replace(" ", "")}

Always use square brackets.
"""

    # ======================================
    # DOCUMENT
    # ======================================

    doc_text = f"""
Table: [{table_name}]

Columns:
{column_text}

Relationships:
{relationship_text}

{table_hint}

Important Rules:
- Use ONLY tables listed in schema.
- Use ONLY columns listed above.
- Never invent columns.
- Never invent tables.
- Use relationships when generating JOINs.
- Use SQL Server syntax only.
- Preserve spaces in table names.
- Wrap tables containing spaces with [].
- Use exact table names.

Example Queries:

SELECT * FROM [{table_name}]

SELECT TOP 10 * FROM [{table_name}]
"""

    schema_docs.append(
        Document(
            page_content=doc_text
        )
    )


# ==========================================
# EMBEDDINGS
# ==========================================

print("\nCreating embeddings...")

embedding = OllamaEmbeddings(
    model="nomic-embed-text"
)

db = Chroma.from_documents(
    documents=schema_docs,
    embedding=embedding,
    persist_directory="./chroma_db"
)

print("\n====================================")
print("Schema + Relationships Loaded")
print("Embeddings Stored Successfully")
print("====================================")
print(f"Tables Indexed: {len(schema_docs)}")

