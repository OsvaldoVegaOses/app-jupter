#!/usr/bin/env python3
"""
Script para detener procesos de la aplicación en puertos específicos.
Detiene backend (8000) y frontend (5173) de forma segura.

Si `uvicorn` se lanza con `--reload`, el watcher puede volver a levantar procesos;
para apagados programables otorga usar `--no-reload` o ejecutar este script con
la opción `--kill-python` para forzar el cierre de todos los `python.exe`.

También puedes usar `--kill-app` para forzar el cierre de los procesos típicos
de la app (python.exe y node.exe).

Uso:
    python scripts/Cerrar_procesos.py [--kill-python|--kill-app]
"""

import subprocess
import sys
import time


def kill_named_processes(image_name: str) -> bool:
    """Forzar cierre de procesos por nombre (ej. python.exe)."""
    try:
        result = subprocess.run(
            ["taskkill", "/IM", image_name, "/F"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"✓ {image_name} detenido")
            return True
        print(f"✗ No se pudo detener {image_name}: {result.stderr.strip()}")
        return False
    except subprocess.CalledProcessError as exc:
        print(f"✗ Error matando {image_name}: {exc}")
        return False


def kill_app_processes() -> int:
    """Forzar cierre de procesos típicos de la app (python/node)."""
    killed = 0
    for image in ("python.exe", "node.exe"):
        if kill_named_processes(image):
            killed += 1
    return killed


def close_port_process(port: int) -> bool:
    """
    Cierra el proceso que está escuchando en un puerto específico.
    
    Args:
        port: Número de puerto
        
    Returns:
        True si se cerró exitosamente, False si no había proceso o error
    """
    try:
        # Obtener PID del proceso en el puerto (Windows)
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=True,
        )
        
        found = False
        for line in result.stdout.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                
                # Matar el proceso
                kill_result = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    text=True,
                )
                
                if kill_result.returncode == 0:
                    print(f"✓ Proceso PID {pid} detenido en puerto {port}")
                    found = True
                else:
                    print(f"✗ Error al detener proceso PID {pid}: {kill_result.stderr}")
        
        if not found:
            print(f"ℹ No hay procesos en puerto {port}")
            return False
            
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Error ejecutando comando: {e}")
        return False
    except (ValueError, IndexError) as e:
        print(f"✗ Error parsing output: {e}")
        return False


def main():
    """Detiene todos los procesos de la aplicación."""
    print("=" * 60)
    print("Cerrando procesos de la aplicación...")
    print("=" * 60)
    
    ports = [8000, 5173]
    closed = 0
    
    for port in ports:
        print(f"\nVerificando puerto {port}...")
        if close_port_process(port):
            closed += 1
        time.sleep(0.5)
    
    print("\n" + "=" * 60)
    if closed > 0:
        print(f"✓ {closed} procesos detenidos exitosamente")
        print("Espera 2 segundos antes de reiniciar...")
        time.sleep(2)
    else:
        print("ℹ No había procesos activos")
    print("=" * 60)


def main_with_python_kill():
    """Apaga puertos y fuerza kill de python.exe para apagar uvicorn --reload."""
    main()
    print("\nDeteniendo procesos python.exe restantes... si los hay")
    kill_named_processes("python.exe")


def main_with_app_kill():
    """Apaga puertos y fuerza kill de procesos típicos de la app."""
    main()
    print("\nDeteniendo procesos de la app (python.exe/node.exe)... si los hay")
    killed = kill_app_processes()
    if killed == 0:
        print("ℹ No se encontraron procesos de la app para detener")


if __name__ == "__main__":
    try:
        if "--kill-app" in sys.argv:
            main_with_app_kill()
        elif "--kill-python" in sys.argv:
            main_with_python_kill()
        else:
            main()
    except KeyboardInterrupt:
        print("\n✗ Cancelado por usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error inesperado: {e}")
        sys.exit(1)
