# Fábrica de Carruseles 🎠

Una skill de [Claude Code](https://claude.com/claude-code) que convierte una idea en un
**carrusel de Instagram listo para publicar**: escribe el copy, genera las imágenes con tu
marca y las sube a Instagram por ti.

Le hablas normal ("hazme un carrusel sobre X") o escribes `/carrusel`, respondes unas preguntas,
y listo.

---

## Qué hace

1. **Onboarding de marca (una sola vez):** te pregunta de qué es tu negocio, tu tono, tus
   colores, tu estilo visual y tu usuario de Instagram.
2. **Escribe el copy** con una estructura que engancha y da valor (gancho → valor → cierre).
3. **Genera las imágenes** con IA (Kie AI, modelo nano-banana-pro), respetando tu marca.
4. **Publica en Instagram** (con Upload Post): te guía a conectar tu cuenta y sube el carrusel por ti.

## Instalación

Necesitas [Claude Code](https://claude.com/claude-code) instalado. Luego, en tu terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/luiscordova-dev/fabrica-carruseles/main/install.sh | bash
```

En **Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/luiscordova-dev/fabrica-carruseles/main/install.ps1 | iex
```

Esto copia la skill a `~/.claude/skills/carrusel/`. Abre Claude Code y escribe `/carrusel`
(o simplemente pídele un carrusel). La skill te guía en el resto, incluido sacar las llaves.

## Qué cuesta

La skill es **gratis**. Para usarla necesitas:
- **Claude Code** (plan Pro).
- **Kie AI** para las imágenes — ~**$0.10 USD por lámina** (un carrusel de 6 ≈ $0.60).
- **Upload Post** para publicar — **gratis** hasta 10 publicaciones al mes (sin tarjeta).

Es normal pagar los servicios que uno usa; la skill te guía para conseguir cada llave.

## Requisito para publicar en Instagram

Instagram solo permite publicar por API desde cuentas **Business o Creator** ligadas a una
página de Facebook (requisito de Meta). La skill te acompaña a dejarlo listo.

## Uso manual (opcional, para técnicos)

```bash
# generar (lee config/marca.json y outputs/<carpeta>/carrusel.md)
python3 scripts/generar.py "outputs/mi-carrusel" --dry-run   # revisar sin gastar
python3 scripts/generar.py "outputs/mi-carrusel"             # generar de verdad

# publicar
python3 scripts/publicar.py "outputs/mi-carrusel" --caption "..." --dry-run
python3 scripts/publicar.py "outputs/mi-carrusel" --caption "..."
```

## Créditos

Motor de generación inspirado en flujos abiertos de generación de carruseles con Kie AI.
Hecho para publicar contenido consistente, rápido.
