import sys
sys.stdout.reconfigure(line_buffering=True)
from app.settings import load_settings

settings = load_settings()
print('1: Settings OK', flush=True)

from openai import AzureOpenAI
print('2: AzureOpenAI imported', flush=True)

# Test AOAI
try:
    aoai = AzureOpenAI(
        azure_endpoint=settings.azure.endpoint,
        api_key=settings.azure.api_key,
        api_version=settings.azure.api_version,
    )
    print('3: AOAI OK', flush=True)
except Exception as e:
    print(f'3: AOAI FAILED: {e}', flush=True)

# Test Qdrant
try:
    from qdrant_client import QdrantClient
    qdrant = QdrantClient(url=settings.qdrant.uri, api_key=settings.qdrant.api_key)
    print('4: Qdrant OK', flush=True)
except Exception as e:
    print(f'4: Qdrant FAILED: {e}', flush=True)

# Test Neo4j
try:
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(settings.neo4j.uri, auth=(settings.neo4j.username, settings.neo4j.password))
    print('5: Neo4j OK', flush=True)
except Exception as e:
    print(f'5: Neo4j FAILED: {e}', flush=True)

# Test Postgres
try:
    import psycopg2
    conn = psycopg2.connect(
        host=settings.postgres.host,
        port=settings.postgres.port,
        dbname=settings.postgres.database,
        user=settings.postgres.username,
        password=settings.postgres.password,
    )
    print('6: Postgres OK', flush=True)
except Exception as e:
    print(f'6: Postgres FAILED: {e}', flush=True)
