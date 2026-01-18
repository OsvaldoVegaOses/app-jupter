---
description: Cómo limpiar el caché de Vite cuando hay problemas de hot-reload
---

# Limpiar Caché de Vite

Cuando Vite no detecta cambios en archivos o muestra código antiguo:

## Opción 1: Limpiar y reiniciar (recomendado)

```powershell
cd frontend
Remove-Item -Recurse -Force node_modules/.vite
npm run dev
```

## Opción 2: Rebuild completo

```powershell
cd frontend
npm run build
npm run dev
```

## Opción 3: Usar flag --force

```powershell
npm run dev -- --force
```

## Cuándo aplicar

- El navegador muestra código antiguo después de editar archivos
- Hot Module Replacement (HMR) no funciona
- Errores de import de módulos que deberían existir
- Cambios en `main.tsx` o `App.tsx` no se reflejan
