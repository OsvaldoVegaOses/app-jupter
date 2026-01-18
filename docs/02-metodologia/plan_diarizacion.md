# Informe y Plan de Solución: Ajuste de Diarización y Segmentación

## 1. Diagnóstico del Problema

### Situación Actual
El sistema actual de ingesta (`app/documents.py`) procesa los documentos de Word párrafo por párrafo de manera independiente ("stateless"). Asume que la identificación del hablante está implícita en el texto mismo (ej. "Entrevistador: ¿Pregunta?") o que el texto pertenece al entrevistado por defecto.

### Hallazgo
Al inspeccionar los archivos fuente (ej. `Claudia_Cesfam.docx`, `Guillermo Orestes.docx`), se detectó que el formato de transcripción separa la identificación del hablante del contenido en líneas distintas, usualmente precedidas por una marca de tiempo.

**Formato observado:**
```text
[Línea N]   00:00:02 David Nuñez, Entrevistador
[Línea N+1] ¿Me dice su nombre, por favor?
[Línea N+2] 00:00:10 Claudia Schwerter
[Línea N+3] Claudia Schwerter Trabajadora social...
```

### Causa Raíz
1.  El sistema lee la **Línea N**. Detecta "Entrevistador", pero como no hay contenido sustancial de texto (solo nombre y hora), a menudo lo descarta o lo procesa como un fragmento vacío.
2.  El sistema lee la **Línea N+1** ("¿Me dice su nombre...?"). Al no tener un prefijo explícito en esa misma línea, el sistema aplica la regla por defecto: **Asignar a Entrevistado**.
3.  **Consecuencia**: Las preguntas del entrevistador se están mezclando con las respuestas del entrevistado, contaminando el análisis semántico y la codificación.

## 2. Plan de Solución ("Stateful Parsing")

Para resolver esto, debemos cambiar la lógica de lectura a un enfoque **basado en estados**. El parser debe recordar quién es el hablante activo hasta que encuentre una nueva marca de cambio de turno.

### Algoritmo Propuesto

Modificar `app/documents.py` -> `read_paragraph_records` con la siguiente lógica:

1.  Inicializar `current_speaker = "interviewee"` (o `unknown`).
2.  Iterar sobre los párrafos del documento.
3.  Para cada párrafo, verificar si es una **Línea de Metadatos** (Timestamp + Nombre):
    *   Patrón Regex: `^\d{1,2}:\d{2}(?::\d{2})?` (detecta `00:00:02`).
    *   Si contiene "Entrevistador", "Moderador" o variantes -> `current_speaker = "interviewer"`.
    *   Si NO contiene esas palabras clave -> `current_speaker = "interviewee"`.
    *   *Acción*: Ignorar esta línea para el contenido, solo actualizar el estado.
4.  Si NO es línea de metadatos (es contenido):
    *   Limpiar el texto.
    *   Asignar `speaker = current_speaker`.
    *   Crear el `ParagraphRecord`.

### Cambios en Código (`app/documents.py`)

#### 1. Nuevas Constantes y Regex
Se añadirán expresiones regulares para detectar las líneas de tiempo y nombres.

```python
_TIMESTAMP_RE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?")
_INTERVIEWER_KEYWORDS = ["entrevistador", "moderador"]
```

#### 2. Refactorización de `read_paragraph_records`
La función dejará de ser una comprensión de lista simple y pasará a ser un bucle con estado.

```python
def read_paragraph_records(path: str | Path) -> List[ParagraphRecord]:
    doc = Document(str(path))
    paragraphs: List[ParagraphRecord] = []
    current_speaker = "interviewee" # Default seguro

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # 1. Detección de Cambio de Turno (Línea de Metadatos)
        if _TIMESTAMP_RE.match(text):
            lower_text = text.lower()
            if any(kw in lower_text for kw in _INTERVIEWER_KEYWORDS):
                current_speaker = "interviewer"
            else:
                current_speaker = "interviewee"
            continue # No guardamos la línea de la hora/nombre como contenido

        # 2. Procesamiento de Contenido
        # Aún limpiamos el texto por si acaso tiene basura
        clean_text = normalize_text(text)
        if clean_text:
             # Filtrado opcional de muletillas del entrevistador si es necesario
             if current_speaker == "interviewer" and _is_filler(clean_text):
                 continue
             
             paragraphs.append(ParagraphRecord(text=clean_text, speaker=current_speaker))

    return paragraphs
```

## 3. Validación

1.  **Prueba Unitaria**: Crear un archivo `.docx` dummy o usar uno existente (`Claudia_Cesfam.docx`).
2.  **Verificación**: Ejecutar el script de lectura y verificar que los textos "¿Me dice su nombre...?" tengan `speaker="interviewer"`.
3.  **Impacto en Ingesta**: Al volver a ejecutar la ingesta, estos párrafos serán filtrados (o marcados correctamente), limpiando la base de datos de ruido.

## 4. Pasos de Ejecución

1.  [ ] Modificar `app/documents.py` implementando la lógica stateful.
2.  [ ] Ejecutar script de prueba (`debug_speaker.py` modificado) para validar la corrección.
3.  [ ] (Opcional) Re-ingerir un archivo para confirmar la limpieza en la base de datos.


He creado el archivo metadata/entrevistas.json con estos valores optimizados:

Parámetro	Valor Anterior	Nuevo Valor	Razón
min_chars	200	             200	         Mantiene filtro de ruido (frases muy cortas)
max_chars	1200	            2000	      Aprovecha mejor el modelo large para capturar ideas más completas
batch_size	64	              64	        Buen equilibrio para velocidad/memoria
Cómo usar esta configuración
En el panel de ingesta (Frontend), en el campo "Archivo Metadata JSON (opcional)", escribe: metadata/entrevistas.json
