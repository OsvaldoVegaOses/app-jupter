
from app.clients import build_service_clients
from app.settings import load_settings
from app.analysis import get_graph_context

def main():
    settings = load_settings()
    clients = build_service_clients(settings)
    
    print("--- GENERATING GRAPHRAG PROMPT EXAMPLE ---\n")
    
    # 1. Fetch live context from Neo4j
    graph_context = get_graph_context(clients, settings)
    
    if not graph_context:
        graph_context = "(No data in graph yet - Simulating empty state)"
        
    # 2. Simulate Fragment
    dummy_fragment = "[IDX: 0] Entrevistado: La inseguridad ha cambiado la forma en que habitamos..."
    
    # 3. Assemble Prompt (Copy logic from analysis.py)
    final_prompt = f"""Analiza la siguiente transcripcion (fuente: DEMO.docx) siguiendo las Etapas 0-4. 
IMPORTANTE: Para cada cita en 'etapa3_matriz_abierta', debes indicar el campo integer 'fragmento_idx' correspondiente al bloque [IDX: n] de donde extrajiste la cita.

{graph_context}

Devuelve SOLO el JSON.

{dummy_fragment}"""

    print(final_prompt)
    print("\n-------------------------------------------")
    clients.close()

if __name__ == "__main__":
    main()
