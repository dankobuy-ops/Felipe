# CLAUDE.md — Apps (GitHub Pages)

Instancia dedicada a crear herramientas web standalone (HTML/CSS/JS puro) y publicarlas en GitHub Pages dentro del repositorio `dankobuy-ops/Apps`.

## Skill activa por defecto

**Siempre que el usuario describa una nueva app a crear, invocar automáticamente el skill `crear-app`.**

```
Skill("crear-app")
```

No esperar confirmación explícita — si el usuario pide una herramienta web o utilidad, activar el skill directamente.

## Repositorio

| Campo | Valor |
|-------|-------|
| Repo GitHub | `dankobuy-ops/Apps` |
| Rama principal | `main` |
| GitHub Pages | activado en `main` / raíz |
| URL base | `https://dankobuy-ops.github.io/Apps/` |

Cada app vive en su propia subcarpeta dentro del repo, excepto la app raíz (`index.html` en `/`).

## Stack

- **Solo** HTML5 + CSS3 + JavaScript ES2022 — sin frameworks, sin bundlers, sin dependencias externas
- Excepción aceptada: CDN de librerías ligeras (Chart.js, Papa Parse, etc.) cuando la app lo requiera
- Codificación siempre **UTF-8**
- Compatibilidad mínima: Chrome / Edge / Firefox últimas 2 versiones

## Estructura de archivos por app

```
Apps/
├── [nombre-app]/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── Archivos/          ← archivos que el usuario sube para pasarle a Claude
└── index.html         ← índice general de todas las apps (mantener actualizado)
```

## Diseño — estándares visuales

- **Dark theme** por defecto (`#0d1117` background, `#161b22` surface)
- Color de acento: `#7c6af7` (violeta) — puede variar por app si hay justificación
- Tipografía: `'Segoe UI', system-ui, sans-serif`
- Totalmente responsivo — mobile first
- Sin frameworks CSS externos (Bootstrap, Tailwind) — CSS vanilla con variables

## Flujo de trabajo para cada app nueva

1. Crear los archivos con las herramientas internas (`Write` / `Edit`) — **nunca inyectar código largo por terminal**
2. Guardar en `C:\Claude\Apps\[nombre-app]/` o en raíz si es app única
3. Hacer `git add` → `git commit` → `git push origin main`
4. Confirmar la URL pública de GitHub Pages al usuario

## Archivos de entrada del usuario

El usuario puede dejar archivos en `C:\Claude\Apps\Archivos\` para que Claude los use como referencia, datos de entrada o contexto al construir una app.

## Recursos compartidos

Archivos y contexto compartido con otras instancias disponible en `C:\Claude\Recursos\`.

## Comandos frecuentes

```powershell
# Ver estado del repo
git -C C:\Claude status Apps/

# Push rápido (SIEMPRE usar remote 'apps', no 'origin')
git -C C:\Claude add Apps/
git -C C:\Claude commit -m "feat: descripción de la app"
git -C C:\Claude push apps main
```

> **Nota de remotes**: `origin` apunta a `dankobuy-ops/Claude` (backup general).
> `apps` apunta a `dankobuy-ops/Apps` (GitHub Pages — usar siempre este).
