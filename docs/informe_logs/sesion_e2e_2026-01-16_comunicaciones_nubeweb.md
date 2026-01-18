# Sesión E2E — comunicaciones@nubeweb.cl (default_org)

**Fecha:** 2026-01-16  
**Fuente:** logs/app.jsonl  
**Usuario:** comunicaciones@nubeweb.cl  
**Org:** default_org  

---

## 1) Registro y autenticación

- **Registro exitoso**
  - 2026-01-16T05:33:57Z → `POST /api/auth/register`
  - Evento: `auth.register.success` (user_id: bbac3d63-6fda-46ab-904c-397f575971e9)

- **Login exitoso**
  - 2026-01-16T13:34:52Z → `POST /api/auth/login`
  - Evento: `auth.login.json.success`
  - `last_login_at`: 2026-01-16T13:34:52Z

---

## 2) Navegación inicial y paneles

Tras login, se observa carga de paneles principales:
- `GET /api/projects`
- `GET /api/status`
- `GET /api/research/overview`
- `GET /api/reports/*`
- `GET /api/stage0/*`

---

## 3) Ingesta E2E (documentos)

### 3.1 Dirigenta_Maria_Sotelo_Puente_Alto_20260116_104312.docx

- **Upload & guardado**
  - 2026-01-16T13:43:12Z → `POST /api/upload-and-ingest`
  - Archivo subido a Blob: `interviews/default/Dirigenta_Maria_Sotelo_Puente_Alto_20260116_104312.docx`

- **Ingesta**
  - 2026-01-16T13:43:25Z → `ingest.file.start`
  - Fragmentos: **26**
  - Qdrant upsert OK
  - `ingest.file.end` OK

### 3.2 Entrevista_Dirigentas_UV_20_La_Florida_20260116_104335.docx

- **Upload & guardado**
  - 2026-01-16T13:43:35Z → `POST /api/upload-and-ingest`
  - Archivo subido a Blob: `interviews/default/Entrevista_Dirigentas_UV_20_La_Florida_20260116_104335.docx`

- **Ingesta**
  - 2026-01-16T13:43:46Z → `ingest.file.start`
  - Fragmentos: **96**
  - Qdrant upsert OK

---

## 4) Observación de orden de segmentos

**Caso reportado:** `Dirigenta_Maria_Sotelo_Puente_Alto_20260116_104312.docx`
- Segmento #8 corresponde al inicio real de la entrevista.
- Los primeros fragmentos contienen preámbulos/metadata del documento.

---

## 5) Acción correctiva propuesta (nuevas ingestas)

En la lógica de lectura DOCX:
- Filtrar **preámbulos** hasta detectar inicio real de diálogo.
- Detección combinada de:
  - timestamps,
  - prefijos de hablante (Entrevistador/Entrevistada),
  - presencia de preguntas.

Esto evita que los encabezados se conviertan en fragmentos 0..N y preserva el orden real del diálogo.

---

## 6) Resultado esperado

- El primer fragmento debe corresponder al **inicio real de la entrevista**.
- Se reduce “ruido” (títulos, metadata, encabezados) en la ingesta.

---

*Documento generado a partir de logs y revisión del pipeline de ingesta.*