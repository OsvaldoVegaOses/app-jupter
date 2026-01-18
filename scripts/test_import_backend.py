"""
Script simple para verificar que el módulo backend.app se puede importar correctamente.
Útil para detectar errores de sintaxis o dependencias faltantes en el entorno.
"""
import importlib,traceback

try:
    importlib.import_module('backend.app')
    print('IMPORT_OK')
except Exception:
    traceback.print_exc()
