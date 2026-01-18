
from app.clients import build_service_clients
from app.settings import load_settings
from app.axial import run_gds_analysis
from app.analysis import get_graph_context
from app.logging_config import configure_logging

def main():
    configure_logging()
    settings = load_settings()
    clients = build_service_clients(settings)
    
    print("--- 1. Testing GDS Persistence (PageRank) ---")
    try:
        # Run PageRank and Persist
        results = run_gds_analysis(clients, settings, "pagerank", persist=True)
        print(f"GDS Executed. Nodes scored: {len(results)}")
        if results:
            print(f"Top 1: {results[0]}")
    except Exception as e:
        print(f"GDS Failed (Expected if GDS plugin not installed): {e}")

    print("\n--- 2. Testing GraphRAG Context Retrieval ---")
    try:
        context = get_graph_context(clients, settings)
        print("Generated Context:")
        print(context)
        
        if "CONTEXTO GLOBAL" in context:
            print("\nSUCCESS: Graph Context Generated.")
        else:
            print("\nWARNING: Context empty (maybe no data in graph?)")
            
    except Exception as e:
        print(f"Context Retrieval Failed: {e}")
    finally:
        clients.close()

if __name__ == "__main__":
    main()
