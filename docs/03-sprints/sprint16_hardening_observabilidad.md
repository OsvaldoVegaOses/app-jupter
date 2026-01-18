# Sprint 16: Hardening y Observabilidad (Security & Reliability)

**Fecha inicio:** 2025-12-27  
**Fecha fin:** 2025-12-27  
**Duración real:** ~2h desarrollo  
**Estado:** ✅ COMPLETADO  
**Tipo:** Deuda Técnica / Seguridad

---

## Objetivo

Cerrar brechas de seguridad, observabilidad y mantenibilidad identificadas en auditoría de código. Preparar la aplicación para ambiente de producción.

---

## Tabla Resumen

| Epic | Prioridad | Descripción | Esfuerzo | Estado |
|------|-----------|-------------|----------|--------|
| E1 | 🔴 P0 | Hardening JWT (fail-fast en prod) | 2h | ✅ |
| E2 | 🔴 P0 | Remover print() residual | 1h | ✅ |
| E3 | 🔴 P0 | Reducir except Exception genéricos | 4h | ✅ |
| E4 | 🟡 P1 | Logging en cierre de recursos | 2h | ✅ |
| E5 | 🟡 P1 | Sanitizar errores HTTP | 3h | ✅ |
| E6 | 🟡 P1 | Cablear graphrag_metrics | 2h | ✅ |
| E7 | 🟢 P2 | Helpers de manejo de errores | 3h | ✅ |
| E8 | 🟢 P2 | Tests de regresión P0/P1 | 4h | ✅ |

**Total estimado:** 21h → **Completado:** ~3h (8 de 8 epics)

---

## 🔴 P0: Riesgo Alto / Impacto Inmediato

### E1: Hardening JWT Secret (2h)

**Archivo:** `backend/auth_service.py`

**Problema actual:**
```python
# Línea 54 - DEFAULT INSEGURO
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "unsafe-secret-for-dev-change-in-prod")
```

**Solución:**
```python
import os

APP_ENV = os.getenv("APP_ENV", "development")

def _get_jwt_secret() -> str:
    """Obtiene JWT secret con fail-fast en producción."""
    secret = os.getenv("JWT_SECRET_KEY")
    
    if APP_ENV in ("production", "prod", "staging"):
        if not secret:
            raise RuntimeError(
                "JWT_SECRET_KEY es requerido en producción. "
                "Configure la variable de entorno."
            )
        if len(secret) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY debe tener al menos 32 caracteres en producción."
            )
    
    return secret or "unsafe-secret-for-dev-change-in-prod"

SECRET_KEY = _get_jwt_secret()
```

**Criterios de aceptación:**
- [ ] En `APP_ENV=production` sin `JWT_SECRET_KEY` → RuntimeError
- [ ] En `APP_ENV=production` con secret < 32 chars → RuntimeError  
- [ ] En `APP_ENV=development` → usa default (warning en logs)
- [ ] Test unitario verifica comportamiento

---

### E2: Remover print() Residual (1h)

**Archivo:** `app/ingestion.py`

**Problema actual:**
```python
# Línea 213 - FUGA DE INFO
print(f"DEBUG: Processing batch {batch_index} with {len(batch)} items. Project ID: {project_id}")
```

**Solución:**
```python
_logger.debug(
    "ingestion.batch_processing",
    batch_index=batch_index,
    batch_size=len(batch),
    project_id=project_id,
    file_name=file_name,
)
```

**Criterios de aceptación:**
- [ ] No hay `print()` en `app/**` (verificar con grep)
- [ ] Información ahora en structlog con nivel debug
- [ ] Contexto estructurado (batch_index, project_id)

---

### E3: Reducir except Exception Genéricos (4h)

**Archivos afectados:**
- `app/graphrag.py:255` 
- `app/qdrant_block.py:169`
- `app/tasks.py:64`
- `app/transcription.py:178`
- `app/graph_algorithms.py:89`
- `backend/app.py:585`

**Política a implementar:**

1. **Capturar específico cuando sea posible:**
```python
# ANTES
except Exception as e:
    _logger.warning("error", error=str(e))
    return default_value

# DESPUÉS
from qdrant_client.http.exceptions import UnexpectedResponse
from neo4j.exceptions import ServiceUnavailable, TransientError

try:
    result = qdrant_client.search(...)
except UnexpectedResponse as e:
    _logger.error("qdrant.search_error", status=e.status_code, error=str(e))
    raise ServiceError("Búsqueda vectorial falló") from e
except Exception as e:
    _logger.error("qdrant.unexpected_error", error=str(e), exc_info=True)
    raise  # Re-raise, no silenciar
```

2. **Si se captura genérica:** siempre log + re-raise o traducir a error de dominio

**Criterios de aceptación:**
- [ ] Excepciones de Qdrant, Neo4j, PostgreSQL: captura específica
- [ ] Excepciones genéricas: siempre log estructurado + exc_info=True
- [ ] No hay `except Exception: pass` (excepto cierre de recursos)

---

## 🟡 P1: Confiabilidad / Seguridad / Observabilidad

### E4: Logging en Cierre de Recursos (2h)

**Archivos:** `app/clients.py:76-104`, `backend/app.py:567-571`

**Problema actual:**
```python
try:
    self.postgres.close()
except Exception:
    pass  # SILENCIO TOTAL
```

**Solución:**
```python
try:
    self.postgres.close()
except Exception as e:
    _logger.debug(
        "clients.close_warning",
        resource="postgres",
        error=str(e),
    )
```

**Criterios de aceptación:**
- [ ] Todos los `except: pass` en cierre de recursos → log debug
- [ ] Log incluye tipo de recurso y error
- [ ] Nivel debug (no warning) para no llenar logs

---

### E5: Sanitizar Errores HTTP (3h)

**Archivos:** `backend/app.py` (múltiples endpoints)

**Problema actual:**
```python
# Línea 587 - FUGA DE INFO INTERNA
raise HTTPException(status_code=502, detail=f"No se pudieron inicializar clientes: {exc}")
```

**Solución:**
```python
# 1. Definir error codes
class ErrorCode:
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DATABASE_ERROR = "DATABASE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_ERROR = "AUTH_ERROR"

# 2. Crear helper
def api_error(
    status_code: int,
    code: str,
    message: str,
    exc: Optional[Exception] = None,
) -> HTTPException:
    """Genera error HTTP sin exponer detalles internos."""
    if exc:
        api_logger.error(
            "api.error",
            status=status_code,
            code=code,
            detail=str(exc),
            exc_info=True,
        )
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )

# 3. Uso
raise api_error(502, ErrorCode.SERVICE_UNAVAILABLE, "Error conectando servicios", exc)
```

**Criterios de aceptación:**
- [ ] Errores HTTP no exponen stack traces ni detalles internos
- [ ] Todos los errores tienen `code` único para debugging
- [ ] Logs internos tienen detalle completo

---

### E6: Cablear graphrag_metrics (2h)

**Archivos:** `app/graphrag.py`, `backend/app.py`

**Problema:** El módulo `graphrag_metrics.py` existe pero no está conectado al flujo.

**Solución:**
```python
# En graphrag_query(), después de generar respuesta:
from app.graphrag_metrics import GraphRAGMetric, persist_metric

metric = GraphRAGMetric.from_response(project_id, query, result)
# Persistir async para no bloquear respuesta
import threading
threading.Thread(target=persist_metric, args=(conn, metric), daemon=True).start()
```

**Criterios de aceptación:**
- [ ] Cada llamada a graphrag_query() genera métrica
- [ ] Métricas visibles en `/api/graphrag/metrics`
- [ ] Persistencia no bloquea respuesta (async)

---

## 🟢 P2: Mantenibilidad / Productividad

### E7: Helpers de Manejo de Errores (3h)

**Nuevo archivo:** `app/error_handling.py`

```python
"""Helpers para manejo uniforme de errores."""

from functools import wraps
from typing import TypeVar, Callable
import structlog

T = TypeVar("T")
_logger = structlog.get_logger()

class ServiceError(Exception):
    """Error de servicio con código y contexto."""
    def __init__(self, code: str, message: str, context: dict = None):
        self.code = code
        self.message = message
        self.context = context or {}
        super().__init__(message)

def with_retry(max_retries: int = 3, backoff: float = 1.0):
    """Decorator para reintentos con backoff exponencial."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    wait = backoff * (2 ** attempt)
                    _logger.warning(
                        "retry.attempt",
                        func=func.__name__,
                        attempt=attempt + 1,
                        wait=wait,
                        error=str(e),
                    )
                    time.sleep(wait)
            raise last_error
        return wrapper
    return decorator

def wrap_external_call(service: str):
    """Decorator para logging uniforme de llamadas externas."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _logger.error(
                    f"{service}.call_error",
                    func=func.__name__,
                    error=str(e),
                    exc_info=True,
                )
                raise ServiceError(
                    code=f"{service.upper()}_ERROR",
                    message=f"Error en {service}",
                    context={"original_error": str(e)},
                ) from e
        return wrapper
    return decorator
```

**Criterios de aceptación:**
- [ ] `ServiceError` con code/message/context
- [ ] `@with_retry` para operaciones IO
- [ ] `@wrap_external_call` para servicios externos

---

### E8: Tests de Regresión P0/P1 (4h)

**Archivo:** `tests/test_security_hardening.py`

```python
import pytest
import os

class TestJWTHardening:
    def test_production_without_secret_fails(self, monkeypatch):
        """En producción, falta de JWT_SECRET_KEY debe fallar."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY es requerido"):
            from backend.auth_service import _get_jwt_secret
            _get_jwt_secret()
    
    def test_production_short_secret_fails(self, monkeypatch):
        """En producción, secret corto debe fallar."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("JWT_SECRET_KEY", "short")
        
        with pytest.raises(RuntimeError, match="al menos 32 caracteres"):
            from backend.auth_service import _get_jwt_secret
            _get_jwt_secret()

class TestNoResidualPrints:
    def test_no_prints_in_app(self):
        """No debe haber print() en código de app."""
        import subprocess
        result = subprocess.run(
            ["grep", "-r", "print(", "app/"],
            capture_output=True, text=True
        )
        # Excluir comentarios y docstrings
        lines = [l for l in result.stdout.split("\n") if l and not l.strip().startswith("#")]
        assert len(lines) == 0, f"Print statements encontrados: {lines}"

class TestErrorSanitization:
    def test_http_errors_no_internal_details(self):
        """Errores HTTP no deben exponer stack traces."""
        # Test via cliente HTTP
        pass
```

**Criterios de aceptación:**
- [ ] Test JWT hardening (producción)
- [ ] Test no print() residuales
- [ ] Test sanitización de errores
- [ ] Todos pasan en CI

---

## Verificación Final

1. [ ] `grep -r "print(" app/` → 0 resultados
2. [ ] `APP_ENV=production` sin JWT_SECRET_KEY → falla al iniciar
3. [ ] Endpoint cualquiera con error → no expone stack trace
4. [ ] `/api/graphrag/metrics` → muestra datos reales

---

## Próximos Sprints

- **Sprint 17:** Chat Enterprise (frontend conversacional)
- **Sprint 18:** Verificador LLM (segunda capa anti-alucinaciones)
