# CibiWiky

Asistente de ciberseguridad con chat. Responde preguntas sobre vulnerabilidades web y cómo prevenirlas o corregirlas, y **cita las fuentes** de cada respuesta.

Proyecto de Sistemas Distribuidos, UABC.

## Cómo funciona

Usa RAG (generación aumentada por recuperación):

1. La pregunta se reformula con el historial del chat para que se entienda sola ("¿y cómo lo mitigo?" pasa a ser una pregunta completa).
2. Se busca en una base vectorial (ChromaDB) con embeddings de Gemini.
3. Los fragmentos poco relevantes se descartan. Si no queda ninguno, el asistente responde que no tiene información.
4. Gemini redacta la respuesta solo con esos fragmentos y los cita como `[1]`, `[2]`.
5. La interfaz muestra únicamente las fuentes que la respuesta citó.

**Base de conocimiento** (contenido de OWASP, en inglés):

- [OWASP Top 10 2025](https://top10.owasp.org/2025/)
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/): 42 hojas con soluciones y buenas prácticas, las ligadas al Top 10.

## Requisitos

- Python 3.10 o superior (probado con 3.14)
- Una API key de [Google AI Studio](https://aistudio.google.com/) (Gemini)
- Conexión a internet para la ingesta inicial

## Instalación

```bash
git clone https://github.com/Botgardo/CibiWiky.git
cd CibiWiky

python -m venv .venv
source .venv/bin/activate        # en fish: source .venv/bin/activate.fish
pip install -r requirements.txt
```

## Configuración

Crea un archivo `.env` en la raíz del proyecto:

```
GEMINI_API_KEY=tu_api_key
SECRET_KEY=una_clave_larga_y_aleatoria
```

Genera una `SECRET_KEY` con:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Variables opcionales:

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Modelo que redacta las respuestas |
| `MAX_DISTANCE` | `0.55` | Distancia máxima para aceptar un fragmento. Más baja = más estricto |
| `TOP_K` | `6` | Fragmentos que se recuperan por pregunta |
| `RAG_DEBUG` | desactivado | Con `1`, imprime en la terminal la búsqueda y las distancias |

> **Importante:** `SECRET_KEY` es obligatoria en cualquier entorno que no sea de pruebas. Sin ella la app usa un valor de desarrollo inseguro.

## Puesta en marcha

Ejecuta todo desde la raíz del proyecto, con el entorno virtual activo.

**1. Crear la base de datos de usuarios y chats**

```bash
flask --app flaskr init-db
```

> Este comando **borra y recrea** las tablas. Úsalo solo la primera vez.

**2. Construir la base de conocimiento**

```bash
python -m flaskr.rag.ingest                  # OWASP Top 10 2025
python -m flaskr.rag.ingest_cheatsheets      # Cheat Sheet Series (unos 13 min)
```

Ambos comandos se pueden reanudar: si se interrumpen, al volver a correrlos saltan lo que ya indexaron.

Opciones útiles:

```bash
python -m flaskr.rag.ingest --reset                       # borra TODA la colección y reconstruye
python -m flaskr.rag.ingest_cheatsheets --dry-run         # cuenta fragmentos sin gastar cuota
python -m flaskr.rag.ingest_cheatsheets --all             # todas las hojas (~140)
python -m flaskr.rag.ingest_cheatsheets --only SQL_Injection_Prevention_Cheat_Sheet
```

> **Cuota de Gemini:** el plan gratuito permite unos 1000 embeddings por día, y cada fragmento cuenta. La ingesta de las 42 hojas usa cerca de 1160, así que puede detenerse con un error 429. No pasa nada: vuelve a correr el comando al día siguiente y continúa donde se quedó. Cada pregunta del chat también consume parte de esa cuota.

**3. Iniciar la aplicación**

```bash
flask --app flaskr run --debug
```

Abre <http://127.0.0.1:5000>, crea una cuenta y empieza un chat.

## Ajustar la relevancia

Si el asistente responde "No encontré información…" a preguntas válidas, el umbral es demasiado estricto; si contesta cosas fuera de tema, es demasiado laxo.

1. Agrega `RAG_DEBUG=1` al `.env` y reinicia.
2. Haz varias preguntas válidas y algunas fuera de tema, y observa en la terminal las líneas `[rag] distancias: [...]`.
3. Fija `MAX_DISTANCE` entre la distancia más alta de las válidas y la más baja de las fuera de tema.

## Estructura

```
flaskr/
├── __init__.py              Fábrica de la app Flask
├── auth.py                  Registro, login y logout
├── chat.py                  Rutas del chat y del endpoint de mensajes
├── db.py, schema.sql        Base de datos SQLite (usuarios, chats, mensajes)
├── rag/
│   ├── ingest.py            Ingesta del OWASP Top 10
│   ├── ingest_cheatsheets.py  Ingesta de las Cheat Sheets
│   └── retriever.py         Búsqueda, filtrado y generación de respuestas
├── templates/               Plantillas HTML (Jinja2)
└── static/style.css         Estilos (modo claro y oscuro)
```

La base vectorial se guarda en `flaskr/rag/chroma/` y la de usuarios en `instance/`. Ninguna se sube a git.

## Seguridad

- El contenido recuperado se trata como material de referencia, no como instrucciones, y se eliminan las etiquetas `<contexto>` de fragmentos, preguntas e historial para que nadie pueda salir del bloque de contexto.
- Las respuestas se insertan en la página como texto, no como HTML.
- Nunca subas tu `.env` ni tu API key al repositorio.

## Limitaciones

- La base solo cubre OWASP; no responde sobre temas fuera de ella.
- El contenido de origen está en inglés y las respuestas se generan en español.
- Es una herramienta de estudio y no sustituye la revisión de un especialista.
- No hay recuperación de contraseña ni límite de intentos de inicio de sesión.

## Fuentes y licencias

El contenido de la base pertenece a [OWASP](https://owasp.org/) y se publica bajo licencias Creative Commons; consulta la licencia vigente en cada sitio. Cada respuesta enlaza a la página de origen.