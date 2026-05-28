from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document
schema_docs = [
    
Document(
    page_content="""
    Table: Customers

    Description:
    Stores customer information.

    Columns:
    CustomerID (string)
    CompanyName (string)
    ContactName (string)
    City (string)
    Region (string)
    PostalCode (string)
    Country (string)
    Phone (string)

    Important:
    PostalCode exists in Customers table.

    Example Queries:
    - customers from Germany
    - customers by country
    - company names and postal codes
    - all Germany companies
    - total companies by country
    """
),

Document(
    page_content="""
    Table: Order Details

    Description:
    Stores product-level order transactions.

    Columns:
    OrderID (int)
    ProductID (int)
    UnitPrice (float)
    Quantity (int)
    Discount (float)

    Relationships:
    [Order Details].OrderID joins Orders.OrderID
    [Order Details].ProductID joins Products.ProductID

    Important:
    Quantity column exists in Order Details table.
    Sales amount can be calculated using:
    UnitPrice * Quantity

    Example Queries:
    - total sales
    - top selling products
    - sales by country
    - monthly sales
    - product revenue
    """
),
Document(
    page_content="""
    Table: Products

    Description:
    Stores product information.

    Columns:
    ProductID (int)
    ProductName (string)
    UnitPrice (float)
    UnitsInStock (int)

    Relationships:
    Products.ProductID joins [Order Details].ProductID

    Example Queries:
    - expensive products
    - products by price
    - top selling products
    """
)
]
embedding = OllamaEmbeddings(
    model="nomic-embed-text"
)
db = Chroma.from_documents(
    schema_docs,
    embedding,
    persist_directory="./chroma_db"
)
print("Schema embeddings stored.")