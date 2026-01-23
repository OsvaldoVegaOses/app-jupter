#!/usr/bin/env python3
""" 
Script para detener procesos de la aplicación en puertos específicos.
Detiene backend (8000) y frontend (Vite: 5173-5180) de forma segura.

Opciones:
    --kill-python  Mata todos los python.exe EXCEPTO este script
    --kill-app     Mata python.exe y node.exe (frontend+backend)
    --kill-node    Mata solo node.exe (frontend)
    (sin args)     Solo cierra procesos en puertos 8000 y 5173-5180

Uso:
    python scripts/Cerrar_procesos.py [--kill-python|--kill-app|--kill-node]
"""

import os
import subprocess
import sys
import time
from typing import List, Set

# PID de este script para no matarnos a nosotros mismos
MY_PID = os.getpid()

# Puertos de la aplicación
# - Backend FastAPI/uvicorn: 8000
# - Frontend Vite: normalmente 5173; si está ocupado, Vite prueba 5174, 5175, ...
APP_PORTS = [8000, *range(5173, 5181)]


def get_pids_by_name(image_name: str) -> List[int]:
    """Obtiene lista de PIDs de procesos por nombre."""
    try:
        # Usar WMIC para obtener PIDs de forma confiable
        result = subprocess.run(
            ["wmic", "process", "where", f"name='{image_name}'", "get", "processid"],
            capture_output=True,
            text=True,
        )
        pids = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
        return pids
    except Exception:
        return []


def get_pids_on_ports(ports: List[int]) -> Set[int]:
    """Obtiene PIDs de procesos escuchando en los puertos especificados."""
    pids = set()
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.split("\n"):
            for port in ports:
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        try:
                            pids.add(int(parts[-1]))
                        except ValueError:
                            pass
    except Exception:
        pass
    return pids


def kill_pid(pid: int, description: str = "") -> bool:
    """Mata un proceso por PID."""
    if pid == MY_PID:
        return False  # No nos matamos a nosotros mismos
    
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            desc = f" ({description})" if description else ""
            print(f"  ✓ PID {pid}{desc} detenido")
            return True
        return False
    except Exception:
        return False


def kill_by_name(image_name: str, exclude_self: bool = True) -> int:
    """Mata procesos por nombre, opcionalmente excluyendo este script."""
    pids = get_pids_by_name(image_name)
    killed = 0
    
    if not pids:
        print(f"  ℹ No hay procesos {image_name}")
        return 0
    
    for pid in pids:
        if exclude_self and pid == MY_PID:
            print(f"  ⊘ PID {pid} (este script) - ignorado")
            continue
        if kill_pid(pid, image_name):
            killed += 1
    
    return killed


def close_ports() -> int:
    """Cierra procesos en los puertos de la aplicación."""
    pids = get_pids_on_ports(APP_PORTS)
    closed = 0
    
    if not pids:
        print("  ℹ Puertos 8000 y 5173-5180 libres")
        return 0
    
    for pid in pids:
        port_info = "puertos 8000 y/o 5173-5180"
        if kill_pid(pid, port_info):
            closed += 1
    
    return closed


def main():
    """Detiene procesos en puertos de la aplicación."""
    print("=" * 50)
    print("🔌 Cerrando procesos en puertos 8000 y 5173-5180...")
    print("=" * 50)
    
    closed = close_ports()
    
    print("-" * 50)
    if closed > 0:
        print(f"✅ {closed} proceso(s) detenido(s)")
    else:
        print("✅ No había procesos activos")
    print("=" * 50)


def main_kill_node():
    """Mata todos los procesos node.exe (frontend)."""
    print("=" * 50)
    print("🟢 Deteniendo Node.js (frontend)...")
    print("=" * 50)
    
    killed = kill_by_name("node.exe", exclude_self=False)
    
    print("-" * 50)
    print(f"✅ {killed} proceso(s) node.exe detenido(s)")
    print("=" * 50)


def main_kill_python():
    """Mata todos los procesos python.exe EXCEPTO este script."""
    print("=" * 50)
    print("🐍 Deteniendo Python (backend/uvicorn)...")
    print(f"   (Este script PID {MY_PID} será preservado)")
    print("=" * 50)
    
    # Primero cerrar puertos
    close_ports()
    time.sleep(0.3)
    
    # Luego matar pythons restantes
    killed = kill_by_name("python.exe", exclude_self=True)
    
    print("-" * 50)
    print(f"✅ {killed} proceso(s) python.exe detenido(s)")
    print("=" * 50)


def main_kill_app():
    """Mata todos los procesos de la app (python + node)."""
    print("=" * 50)
    print("🛑 Deteniendo TODA la aplicación...")
    print(f"   (Este script PID {MY_PID} será preservado)")
    print("=" * 50)
    
    # Primero cerrar puertos
    print("\n📍 Liberando puertos...")
    port_closed = close_ports()
    time.sleep(0.3)
    
    # Matar node (frontend)
    print("\n🟢 Deteniendo Node.js...")
    node_killed = kill_by_name("node.exe", exclude_self=False)
    
    # Matar python (backend) excepto este script
    print("\n🐍 Deteniendo Python...")
    python_killed = kill_by_name("python.exe", exclude_self=True)
    
    # Esperar un momento para que los procesos terminen
    time.sleep(0.5)
    
    # Verificar que puertos estén libres
    remaining = get_pids_on_ports(APP_PORTS)
    
    print("\n" + "-" * 50)
    total = port_closed + node_killed + python_killed
    print(f"✅ Total: {total} proceso(s) detenido(s)")
    if remaining:
        print(f"⚠️  Aún hay {len(remaining)} proceso(s) en puertos")
    else:
        print("✅ Puertos 8000 y 5173-5180 libres")
    print("=" * 50)


if __name__ == "__main__":
    try:
        if "--kill-app" in sys.argv:
            main_kill_app()
        elif "--kill-python" in sys.argv:
            main_kill_python()
        elif "--kill-node" in sys.argv:
            main_kill_node()
        else:
            main()
    except KeyboardInterrupt:
        print("\n✗ Cancelado por usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error inesperado: {e}")
        sys.exit(1)
