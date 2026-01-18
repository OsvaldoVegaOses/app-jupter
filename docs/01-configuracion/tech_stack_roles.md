# Roles de Tecnología en la Arquitectura

Este documento describe la responsabilidad específica de cada tecnología en el stack "Hybrid Neuro-Symbolic" de la aplicación.

## 1. Bases de Datos (La Tríada de Datos)
La aplicación utiliza tres bases de datos especializadas. Ninguna es redundante; cada una modela la realidad desde una perspectiva distinta.

### 🐘 PostgreSQL (La Verdad Relacional)
*   **Rol**: Almacén primario y "Fuente de la Verdad".
*   **Qué guarda**: 
    *   Transgripciones crudas (texto completo).
    *   Metadatos duros (fechas, autores, IDs).
    *   Tablas de códigos y usuarios.
*   **Por qué**: Garantiza integridad referencial y permite consultas SQL estándar para estadísticas y reportes tabulares.

### 🕸️ Neo4j (La Lógica del Grafo)
*   **Rol**: Motor de complejidad y relaciones.
*   **Qué guarda**: 
    *   Nodos (`Fragmento`, `Codigo`, `Categoria`, `Persona`).
    *   Relaciones (`(:Fragmento)-[:TIENE_CODIGO]->(:Codigo)`).
*   **Por qué**: Es el único capaz de responder preguntas complejas como *"¿Qué temas conectan a los entrevistados de la zona Norte con los de la zona Sur?"* mediante algoritmos de grafos (PageRank, Louvain).

### 🚀 Qdrant (La Búsqueda Semántica)
*   **Rol**: Memoria asociativa (Vector Database).
*   **Qué guarda**: 
    *   Embeddings (representación matemática) de cada párrafo.
*   **Por qué**: Permite buscar **por significado**, no por palabras clave.
    *   *Ejemplo*: Si buscas "pobreza", Qdrant encontrará fragmentos que hablen de "escasez de recursos" o "falta de dinero", aunque no digan la palabra "pobreza".

---

## 2. Backend & Procesamiento

### ⚡ FastAPI (El Sistema Nervioso)
*   **Rol**: Orquestador y API Gateway.
*   **Función**: Recibe las peticiones del Frontend, verifica seguridad (Auth) y decide a qué agente delegar la tarea.

### 🥦 Celery + Redis (El Músculo Asíncrono)
*   **Rol**: Procesamiento en segundo plano (Background Workers).
*   **Redis**: Es el "buzón" (Broker) donde se dejan los mensajes de tareas pendientes.
*   **Celery**: Es el "obrero" que recoge los mensajes y ejecuta tareas pesadas (como analizar una entrevista de 1 hora con GPT-5) sin que el usuario tenga que esperar con la pantalla congelada.

### 🧠 Azure OpenAI (El Cerebro)
*   **Rol**: Inteligencia Cognitiva.
*   **Modelos**:
    *   **Embeddings**: Para convertir texto a números (usado por Qdrant).
    *   **GPT-4o/5**: Para "razonar" sobre el texto, sugerir códigos y redactar resúmenes.

---

## 3. Frontend

### ⚛️ React + Vite (La Interfaz)
*   **Rol**: Visualización e Interacción.
*   **Graph Visualization**: Usa librerías de fuerza (`react-force-graph`) para "dibujar" los datos de Neo4j, permitiendo al investigador "tocar" y explorar las conexiones teóricas.

---

## Resumen de Flujo
1.  **React** envía el texto a **FastAPI**.
2.  **FastAPI** lo pasa a **Celery**.
3.  **Celery** usa **Azure OpenAI** para entenderlo.
4.  El resultado se guarda fragmentado en **Postgres** (texto), **Qdrant** (significado) y **Neo4j** (conexiones).
