"""Debug script to check fragment context bug."""
import sys
from app.clients import build_service_clients
from app.settings import load_settings


OUTPUT_FILE = "scripts/debug_output.txt"


def log(msg):
    print(msg)
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    # Clear output file
    open(OUTPUT_FILE, "w", encoding="utf-8").close()
    settings = load_settings()
    clients = build_service_clients(settings)
    
    try:
        # 1. Verificar el contenido del fragmento problemático
        fragment_id = "024a5b6e-42a2-56d1-b02b-65ac8d77796d"
        project = "horcon"
        
        log("=" * 80)
        log(f"INVESTIGANDO FRAGMENTO: {fragment_id}")
        log("=" * 80)
        
        # Buscar el fragmento en entrevista_fragmentos
        with clients.postgres.cursor() as cur:
            cur.execute("""
                SELECT id, par_idx, fragmento, speaker, archivo
                FROM entrevista_fragmentos
                WHERE id = %s AND project_id = %s
            """, (fragment_id, project))
            row = cur.fetchone()
            
        if row:
            log("\n[1] FRAGMENTO EN entrevista_fragmentos:")
            log(f"    ID: {row[0]}")
            log(f"    par_idx: {row[1]}")
            log(f"    archivo: {row[4]}")
            log(f"    speaker: {row[3]}")
            log(f"    fragmento (primeros 500 chars):\n    {row[2][:500]}...")
        else:
            log(f"\n[1] FRAGMENTO NO ENCONTRADO con ID: {fragment_id}")
        
        # 2. Buscar las citas asociadas a este fragmento en analisis_codigos_abiertos
        with clients.postgres.cursor() as cur:
            cur.execute("""
                SELECT codigo, cita, fuente, created_at
                FROM analisis_codigos_abiertos
                WHERE fragmento_id = %s AND project_id = %s
            """, (fragment_id, project))
            citas = cur.fetchall()
        
        log("\n[2] CITAS ASIGNADAS A ESTE FRAGMENTO:")
        if citas:
            for c in citas:
                log(f"    Código: {c[0]}")
                log(f"    Cita: '{c[1]}'")
                log(f"    Fuente: {c[2]}")
                log(f"    Creado: {c[3]}")
                log("-" * 40)
        else:
            log("    No hay citas asignadas a este fragmento")
        
        # 3. Buscar si la cita "llega el pueblo entero" existe en OTRO fragmento
        cita_buscada = "llega el pueblo entero"
        log(f"\n[3] BUSCANDO '{cita_buscada}' EN TODOS LOS FRAGMENTOS:")
        with clients.postgres.cursor() as cur:
            cur.execute("""
                SELECT id, par_idx, fragmento, speaker
                FROM entrevista_fragmentos
                WHERE project_id = %s 
                  AND fragmento ILIKE %s
                ORDER BY par_idx
            """, (project, f"%{cita_buscada}%"))
            matches = cur.fetchall()
        
        if matches:
            for m in matches:
                log(f"    ENCONTRADO en fragmento: {m[0]}")
                log(f"    par_idx: {m[1]}")
                log(f"    speaker: {m[3]}")
                # Mostrar contexto alrededor de la cita
                start_idx = m[2].lower().find(cita_buscada.lower())
                if start_idx >= 0:
                    context_start = max(0, start_idx - 100)
                    context_end = min(len(m[2]), start_idx + len(cita_buscada) + 100)
                    log(f"    Contexto: ...{m[2][context_start:context_end]}...")
                log("-" * 40)
        else:
            log(f"    NO SE ENCONTRÓ ningún fragmento con '{cita_buscada}'")
            
    finally:
        clients.close()


if __name__ == "__main__":
    main()
