# CLAUDE.md — Otros

Instancia de propósito general para tareas que no pertenecen al proyecto SGA ni a la creación de apps web. Sin restricciones de stack ni dominio.

## Propósito

Espacio de trabajo libre para:
- Scripts de automatización (Python, PowerShell, Bash)
- Procesamiento y análisis de datos
- Consultas, investigación y documentación
- Prototipos rápidos de cualquier tecnología
- Tareas de sistema y utilidades varias
- Cualquier trabajo que no encaje en SGA ni Apps

## Archivos de entrada del usuario

El usuario puede dejar archivos en `C:\Claude\Otros\Archivos\` para que Claude los use como punto de partida, datos de análisis o contexto de trabajo.

## Recursos compartidos

Archivos y contexto compartido con otras instancias disponible en `C:\Claude\Recursos\`.

## Instancias activas del sistema

| Instancia | Carpeta | Propósito |
|-----------|---------|-----------|
| SGA | `C:\Claude\SGA\` | Sistema de gestión de seguros (FastAPI + PostgreSQL + React) |
| Apps | `C:\Claude\Apps\` | Herramientas web HTML/CSS/JS → GitHub Pages |
| Otros | `C:\Claude\Otros\` | Esta instancia — uso general |

## Convenciones generales

- Preferir soluciones simples y directas antes que arquitecturas complejas
- Para scripts de un solo uso: no agregar manejo de errores innecesario
- Documentar solo lo no obvio
- Si la tarea encaja mejor en SGA o Apps, indicárselo al usuario y sugerir cambiar de instancia
