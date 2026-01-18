import os
import asyncio
from dotenv import load_dotenv
from app.settings import get_settings
from app.clients import build_neo4j_only

async def count_nodes():
    load_dotenv()
    settings = get_settings()
    clients = build_neo4j_only(settings)
    try:
        query = "MATCH (n) RETURN count(n) as count"
        result = clients.neo4j.session(database=settings.neo4j.database).run(query).single()
        print(f"Total Nodes in DB '{settings.neo4j.database}': {result['count']}")
        
        query_labels = "CALL db.labels()"
        labels = clients.neo4j.session(database=settings.neo4j.database).run(query_labels).value()
        print(f"Labels: {labels}")
        
    finally:
        clients.close()

if __name__ == "__main__":
    asyncio.run(count_nodes())
