#!/usr/bin/env python3
import json
from app.settings import load_settings
from app.clients import build_service_clients

def main():
    s = load_settings()
    clients = build_service_clients(s)
    pg = clients.postgres
    out = {}
    try:
        cur = pg.cursor()
        cur.execute("SELECT pg_typeof(evidencia)::text AS tipo, count(*) FROM analisis_axial GROUP BY tipo ORDER BY count DESC")
        out['types'] = cur.fetchall()

        cur.execute("SELECT id, pg_typeof(evidencia)::text AS tipo, evidencia FROM analisis_axial WHERE evidencia IS NOT NULL LIMIT 200")
        rows = cur.fetchall()
        sample_problematic = []
        allowed = {'text[]','json','jsonb'}
        for r in rows:
            tid, tipo, evidencia = r[0], r[1], r[2]
            if tipo not in allowed:
                sample_problematic.append({'id':tid,'tipo':tipo,'evidencia_preview': str(evidencia)[:400]})
            else:
                if tipo in {'json','jsonb'}:
                    try:
                        import json as _j
                        parsed = _j.loads(evidencia) if isinstance(evidencia, str) else evidencia
                        if isinstance(parsed, list) and parsed:
                            first = parsed[0]
                            if isinstance(first, dict):
                                if 'fragmento_id' not in first and 'fragmento' not in first:
                                    sample_problematic.append({'id':tid,'tipo':tipo,'issue':'json_missing_fragmento_id_key','evidencia_preview':str(parsed)[:400]})
                    except Exception as e:
                        sample_problematic.append({'id':tid,'tipo':tipo,'issue':'json_parse_error','error':str(e),'evidencia_preview':str(evidencia)[:400]})

        out['problematic_samples'] = sample_problematic[:100]
        if not out['problematic_samples']:
            cur.execute("SELECT id, pg_typeof(evidencia)::text AS tipo, evidencia FROM analisis_axial WHERE evidencia IS NOT NULL LIMIT 20")
            out['examples']= [{'id':r[0],'tipo':r[1],'evidencia_preview':str(r[2])[:400]} for r in cur.fetchall()]
        cur.close()
    finally:
        clients.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
