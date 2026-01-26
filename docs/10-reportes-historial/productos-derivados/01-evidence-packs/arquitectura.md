# Arquitectura (Evidence Packs)

## Objetivo
Convertir salidas del baseline (hallazgos/códigos/relaciones/evidencia) en paquetes consistentes, auditables y exportables.

## Componentes
- **Generador de paquetes**: produce documentos por plantilla (hallazgo→evidencia→interpretación→recomendación)
- **Capa de anonimización**: políticas por proyecto/cliente
- **Manifest/QA**: checksum + controles (cobertura, trazabilidad mínima)

## Interfaces
- Entrada: proyecto + parámetros (tema/categoría, límites, anonimización)
- Salida: carpeta con artefactos + manifest
