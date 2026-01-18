#!/usr/bin/env python3
"""
Script de pruebas de carga para análisis LLM.

Ejecuta análisis LLM concurrente en múltiples archivos y mide throughput.

Uso:
    python scripts/load_test_analyze.py --project test-carga --limit 10

Opciones:
    --project: Proyecto (default: load-test)
    --limit: Limitar número de archivos a analizar
    --concurrency: Análisis concurrentes (default: 2)
    --model: Modelo LLM a usar (usa el de config si no se especifica)
"""

import argparse
import time
import json
import sys
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import requests

API_BASE = "http://localhost:8000"


def get_auth_headers() -> dict:
    """Obtiene headers de autenticación."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("API_KEY") or os.getenv("NEO4J_API_KEY", "")
    return {"X-API-Key": api_key, "Content-Type": "application/json"}


def get_project_interviews(project: str) -> List[str]:
    """Obtiene lista de entrevistas del proyecto."""
    headers = get_auth_headers()
    response = requests.get(
        f"{API_BASE}/api/coding/interviews",
        params={"project": project},
        headers=headers,
        timeout=30,
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("interviews", [])
    return []


def analyze_single_file(
    filename: str,
    project: str,
    async_mode: bool = True,
) -> Dict[str, Any]:
    """Analiza un archivo y retorna métricas."""
    headers = get_auth_headers()
    start_time = time.time()
    
    result = {
        "file": filename,
        "success": False,
        "duration_seconds": 0,
        "codes_generated": 0,
        "categories": 0,
        "task_id": None,
        "error": None,
    }
    
    try:
        payload = {
            "filename": filename,
            "project": project,
        }
        
        if async_mode:
            # Usar endpoint async
            response = requests.post(
                f"{API_BASE}/api/analyze/async",
                json=payload,
                headers=headers,
                timeout=30,
            )
            
            if response.status_code == 200:
                data = response.json()
                result["task_id"] = data.get("task_id")
                result["success"] = True
        else:
            # Análisis síncrono (bloquea)
            response = requests.post(
                f"{API_BASE}/api/analyze",
                json=payload,
                headers=headers,
                timeout=300,  # 5 min timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                result["success"] = True
                result["codes_generated"] = len(data.get("codigos", []))
                result["categories"] = len(data.get("categorias", []))
            else:
                result["error"] = response.text[:200]
                
    except Exception as e:
        result["error"] = str(e)
    
    result["duration_seconds"] = round(time.time() - start_time, 2)
    return result


def wait_for_tasks(task_ids: List[str], timeout: int = 600) -> Dict[str, Any]:
    """Espera a que todos los tasks async completen."""
    headers = get_auth_headers()
    start_time = time.time()
    completed = 0
    failed = 0
    
    pending = set(task_ids)
    results = {}
    
    while pending and (time.time() - start_time) < timeout:
        for task_id in list(pending):
            try:
                response = requests.get(
                    f"{API_BASE}/api/analyze/status/{task_id}",
                    headers=headers,
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "")
                    
                    if status == "SUCCESS":
                        pending.discard(task_id)
                        completed += 1
                        results[task_id] = data.get("result", {})
                    elif status in ("FAILURE", "REVOKED"):
                        pending.discard(task_id)
                        failed += 1
            except Exception:
                pass
        
        if pending:
            time.sleep(2)  # Poll cada 2 segundos
    
    return {
        "completed": completed,
        "failed": failed,
        "timed_out": len(pending),
        "total_wait_seconds": round(time.time() - start_time, 2),
        "results": results,
    }


def run_load_test(
    interviews: List[str],
    project: str,
    concurrency: int = 2,
    async_mode: bool = True,
) -> Dict[str, Any]:
    """Ejecuta prueba de carga de análisis."""
    
    total_start = time.time()
    results = []
    task_ids = []
    
    print(f"\n📊 Prueba de Carga: Análisis LLM")
    print(f"   Proyecto: {project}")
    print(f"   Archivos: {len(interviews)}")
    print(f"   Concurrencia: {concurrency}")
    print(f"   Modo: {'Async' if async_mode else 'Sync'}")
    print("-" * 50)
    
    if concurrency == 1:
        # Secuencial
        for i, filename in enumerate(interviews):
            print(f"\n[{i+1}/{len(interviews)}] Analizando {filename}...", end=" ", flush=True)
            result = analyze_single_file(filename, project, async_mode)
            results.append(result)
            
            if result["success"]:
                if async_mode:
                    task_ids.append(result["task_id"])
                    print(f"✓ Task: {result['task_id'][:8]}...")
                else:
                    print(f"✓ {result['codes_generated']} códigos, {result['categories']} categorías")
            else:
                print(f"✗ Error: {result['error'][:40]}")
    else:
        # Concurrente
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(
                    analyze_single_file, f, project, async_mode
                ): f for f in interviews
            }
            
            for i, future in enumerate(as_completed(futures)):
                filename = futures[future]
                result = future.result()
                results.append(result)
                
                if result["success"] and async_mode and result["task_id"]:
                    task_ids.append(result["task_id"])
                
                status = "✓" if result["success"] else "✗"
                print(f"[{i+1}/{len(interviews)}] {status} {result['file'][:30]}: {result['duration_seconds']}s")
    
    # Si es async, esperar resultados
    async_results = {}
    if async_mode and task_ids:
        print(f"\n⏳ Esperando {len(task_ids)} tareas async...")
        async_results = wait_for_tasks(task_ids, timeout=600)
        print(f"   Completados: {async_results['completed']}")
        print(f"   Fallidos: {async_results['failed']}")
        print(f"   Timeout: {async_results['timed_out']}")
    
    total_duration = time.time() - total_start
    
    # Calcular métricas
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    summary = {
        "timestamp": datetime.now().isoformat(),
        "project": project,
        "total_files": len(interviews),
        "submitted": len(successful),
        "failed_submit": len(failed),
        "total_duration_seconds": round(total_duration, 2),
        "throughput_files_per_minute": round(len(successful) / (total_duration / 60), 2) if total_duration > 0 else 0,
        "concurrency": concurrency,
        "async_mode": async_mode,
        "async_results": async_results if async_mode else None,
        "errors": [{"file": r["file"], "error": r["error"]} for r in failed],
    }
    
    # Imprimir resumen
    print("\n" + "=" * 50)
    print("📈 RESUMEN DE PRUEBA DE CARGA")
    print("=" * 50)
    print(f"   Archivos enviados:   {summary['submitted']}/{summary['total_files']}")
    print(f"   Duración total:      {summary['total_duration_seconds']}s")
    print(f"   Throughput submit:   {summary['throughput_files_per_minute']} archivos/min")
    
    if async_results:
        print(f"\n   Análisis completados: {async_results['completed']}")
        print(f"   Análisis fallidos:    {async_results['failed']}")
        print(f"   Tiempo de espera:     {async_results['total_wait_seconds']}s")
    
    if failed:
        print(f"\n⚠️  {len(failed)} errores de envío:")
        for err in summary["errors"][:3]:
            print(f"      - {err['file']}: {err['error'][:50]}")
    
    return summary


def main():
    parser = argparse.ArgumentParser(description="Prueba de carga para análisis LLM")
    parser.add_argument("--project", type=str, default="load-test", help="Proyecto")
    parser.add_argument("--limit", type=int, default=None, help="Limitar archivos")
    parser.add_argument("--concurrency", type=int, default=2, help="Análisis concurrentes")
    parser.add_argument("--sync", action="store_true", help="Usar modo síncrono (bloquea)")
    parser.add_argument("--output", type=str, default=None, help="Guardar resultados")
    
    args = parser.parse_args()
    
    # Obtener entrevistas del proyecto
    print(f"🔍 Obteniendo entrevistas del proyecto '{args.project}'...")
    interviews = get_project_interviews(args.project)
    
    if not interviews:
        print(f"❌ No se encontraron entrevistas en el proyecto '{args.project}'")
        print("   Primero ingesta archivos con: python scripts/load_test_ingest.py")
        return 1
    
    print(f"   Encontradas: {len(interviews)} entrevistas")
    
    if args.limit:
        interviews = interviews[:args.limit]
        print(f"   Limitando a: {len(interviews)}")
    
    # Ejecutar prueba
    summary = run_load_test(
        interviews=interviews,
        project=args.project,
        concurrency=args.concurrency,
        async_mode=not args.sync,
    )
    
    # Guardar resultados
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Resultados guardados en {output_path}")
    else:
        # Guardar automáticamente
        report_path = Path(f"logs/loadtest_analyze_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        report_path.parent.mkdir(exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Reporte guardado en {report_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
