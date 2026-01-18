# Plan de Mejora UX/UI
**Fecha:** 2025-12-21  
**Basado en:** Lecciones aprendidas de la sesión de debugging del CodeValidationPanel  
**Estado:** ✅ Implementado (Prioridad Alta y Media)

---

## 1. Objetivo

Implementar mejoras en la arquitectura y UX del dashboard para:
- Prevenir errores silenciosos
- Mejorar el feedback visual al usuario
- Facilitar el debugging en desarrollo
- Aumentar la resiliencia del sistema

---

## 2. Mejoras Propuestas

### 🔴 Prioridad Alta (Sprint Inmediato)

#### 2.1 Indicador de Estado del Backend

**Descripción:** Widget visual que muestre el estado de conexión con el backend.

**Ubicación:** Header del dashboard

**Implementación:**
```tsx
// components/BackendStatus.tsx
export function BackendStatus() {
  const [status, setStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  
  useEffect(() => {
    const checkBackend = async () => {
      try {
        await fetch('/healthz');
        setStatus('online');
      } catch {
        setStatus('offline');
      }
    };
    checkBackend();
    const interval = setInterval(checkBackend, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className={`status-indicator status--${status}`}>
      <span className="status-dot" />
      {status === 'online' ? 'Backend conectado' : 
       status === 'offline' ? '⚠️ Sin conexión al servidor' : 
       'Verificando...'}
    </div>
  );
}
```

**Esfuerzo:** 2 horas  
**Archivos:** `components/BackendStatus.tsx`, `App.tsx`, `App.css`  
**Estado:** ✅ **IMPLEMENTADO** - Ver `frontend/src/components/BackendStatus.tsx`

---

#### 2.2 Error Boundaries para Paneles

**Descripción:** Envolver cada panel en un Error Boundary que capture errores de renderizado.

**Beneficio:** Evitar que un error en un componente colapse toda la app.

**Implementación:**
```tsx
// components/PanelErrorBoundary.tsx
class PanelErrorBoundary extends React.Component {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="panel-error">
          <h4>⚠️ Error en este panel</h4>
          <p>{this.state.error?.message}</p>
          <button onClick={() => this.setState({ hasError: false })}>
            Reintentar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

**Esfuerzo:** 3 horas  
**Archivos:** `components/PanelErrorBoundary.tsx`, todos los paneles en `App.tsx`  
**Estado:** ✅ **IMPLEMENTADO** - Ver `frontend/src/components/PanelErrorBoundary.tsx`

---

#### 2.3 Manejo de Errores Visibles en API

**Descripción:** Modificar `apiFetch` para mostrar toasts automáticos en errores.

**Implementación:**
```tsx
// services/api.ts
export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  try {
    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      const errorDetail = await response.text();
      // Disparar toast global
      window.dispatchEvent(new CustomEvent('api-error', { 
        detail: { status: response.status, message: errorDetail, path }
      }));
      throw new Error(errorDetail || `Error ${response.status}`);
    }
    return response;
  } catch (err) {
    if (err.name === 'TypeError' && err.message === 'Failed to fetch') {
      window.dispatchEvent(new CustomEvent('api-error', { 
        detail: { status: 0, message: 'No se pudo conectar al servidor', path }
      }));
    }
    throw err;
  }
}
```

**Esfuerzo:** 2 horas  
**Archivos:** `services/api.ts`, `App.tsx` (listener de eventos)  
**Estado:** ✅ **IMPLEMENTADO** - Ver `frontend/src/services/api.ts` y `frontend/src/components/ApiErrorToast.tsx`

---

### 🟡 Prioridad Media (Próximo Sprint)

#### 2.4 Loading States con Skeletons

**Descripción:** Reemplazar "Cargando..." con skeletons animados.

**Componentes afectados:**
- CodeValidationPanel
- CodingPanel
- DiscoveryPanel
- ReportsPanel

**Esfuerzo:** 4 horas  
**Estado:** ✅ **IMPLEMENTADO** - Ver `frontend/src/components/Skeleton.tsx`

---

#### 2.5 Retry Logic con Exponential Backoff

**Descripción:** Reintentar automáticamente llamadas fallidas con backoff.

```tsx
async function fetchWithRetry(fn, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (err) {
      if (i === maxRetries - 1) throw err;
      await new Promise(r => setTimeout(r, Math.pow(2, i) * 1000));
    }
  }
}
```

**Esfuerzo:** 2 horas  
**Estado:** ✅ **IMPLEMENTADO** - Ver `frontend/src/services/api.ts` (RetryOptions)

---

#### 2.6 Script de Validación de Entorno

**Descripción:** Script que valide la configuración antes de iniciar.

```bash
# scripts/validate_env.sh
#!/bin/bash
echo "🔍 Validando configuración..."

# Verificar .env del frontend
if ! grep -q "VITE_API_BASE=http://127.0.0.1:8000" frontend/.env; then
  echo "❌ Error: VITE_API_BASE debe apuntar al puerto 8000"
  exit 1
fi

# Verificar que PostgreSQL esté accesible
if ! pg_isready -h localhost -p 5432; then
  echo "❌ Error: PostgreSQL no está disponible"
  exit 1
fi

echo "✅ Configuración válida"
```

**Esfuerzo:** 1 hora  
**Estado:** ✅ **IMPLEMENTADO** - Ver `scripts/validate_env.ps1`

---

### 🟢 Prioridad Baja (Backlog)

#### 2.8 AUTH gate para Briefing IA (anonimización contextual + validación)

**Descripción:** Guardas éticas/metodológicas para que el “Briefing IA” pueda guardarse (y especialmente validarse) solo si se aplicó anonimización contextual y checklist mínimo anti-sesgo.

**Archivos:**
- `frontend/src/components/AnalysisPanel.tsx`
- `POST /api/analyze/persist` (validación suave opcional)
- Especificación: `docs/05-calidad/auth_task_briefing_plus.md`

**Estado:** 🟡 **EN BACKLOG**

#### 2.7 Dashboard de Salud del Sistema

**Descripción:** Panel administrativo que muestre:
- Estado de cada servicio (Backend, Neo4j, PostgreSQL, Qdrant)
- Latencia de APIs
- Errores recientes
- Uso de recursos

**Esfuerzo:** 8 horas  
**Estado:** ✅ **IMPLEMENTADO** - Ver `frontend/src/components/SystemHealthDashboard.tsx` y endpoint `/api/health/full`

---

#### 2.8 Testing E2E con Playwright

**Descripción:** Suite de tests automatizados que validen flujos completos.

```typescript
// tests/e2e/validation-panel.spec.ts
test('CodeValidationPanel should render', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('text=Bandeja de Códigos Candidatos')).toBeVisible();
});

test('Propose code from Discovery should work', async ({ page }) => {
  await page.goto('/');
  await page.fill('[data-testid="discovery-input"]', 'test query');
  await page.click('text=Buscar');
  await page.click('text=Proponer Código');
  await expect(page.locator('text=Código propuesto')).toBeVisible();
});
```

**Esfuerzo:** 12 horas  
**Estado:** ✅ **IMPLEMENTADO** - Ver `frontend/tests/e2e/` y `frontend/playwright.config.ts`

---

## 3. Cronograma Propuesto

```
┌──────────────────────────────────────────────────────────────┐
│                    CRONOGRAMA DE MEJORAS                      │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  SEMANA 1                                                     │
│  ├── [2h] Indicador de estado del backend                    │
│  ├── [3h] Error Boundaries para paneles                      │
│  └── [2h] Manejo de errores visibles en API                  │
│                                                               │
│  SEMANA 2                                                     │
│  ├── [4h] Loading states con skeletons                       │
│  ├── [2h] Retry logic con exponential backoff                │
│  └── [1h] Script de validación de entorno                    │
│                                                               │
│  BACKLOG                                                      │
│  ├── [8h] Dashboard de salud del sistema                     │
│  └── [12h] Testing E2E con Playwright                        │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Métricas de Éxito

| Métrica | Valor Actual | Objetivo |
|---------|--------------|----------|
| Tiempo de detección de errores | ~50 min | < 5 min |
| Feedback visual en errores | 0% | 100% |
| Componentes con Error Boundary | 0 | Todos |
| Cobertura E2E | 0% | > 60% |

---

## 5. Checklist de Implementación de Features

### Para Nuevos Componentes

```markdown
## Checklist: [Nombre del Componente]

### Backend
- [ ] Modelo Pydantic definido
- [ ] Endpoint(s) implementado(s) en `backend/app.py`
- [ ] Funciones importadas de `postgres_block.py` (si aplica)
- [ ] Endpoint devuelve 200 OK en test manual

### Frontend
- [ ] Funciones de servicio en `services/api.ts`
- [ ] Componente creado en `components/`
- [ ] Componente importado en `App.tsx`
- [ ] Componente renderizado en ubicación correcta
- [ ] Estado de loading implementado
- [ ] Estado de error implementado (visible al usuario)
- [ ] Error Boundary aplicado

### Configuración
- [ ] Variables de entorno documentadas
- [ ] Puerto de API correcto en `frontend/.env`
- [ ] Servidor de desarrollo reiniciado

### Testing
- [ ] Test manual: Componente visible
- [ ] Test manual: Funcionalidad principal
- [ ] Console libre de errores
```

---

## 6. Responsables

| Tarea | Responsable | Fecha Límite |
|-------|-------------|--------------|
| Indicador de backend | TBD | - |
| Error Boundaries | TBD | - |
| Manejo de errores API | TBD | - |

---

## 7. Revisión

- **Próxima revisión:** Después de implementar items de Prioridad Alta
- **Criterio de éxito:** Cero errores silenciosos en nuevas funcionalidades

---

**Estado:** ✅ Completado - Todas las mejoras implementadas
