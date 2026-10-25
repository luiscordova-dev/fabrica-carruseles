# Fábrica de Carruseles 🎠

Una skill de [Claude Code](https://claude.com/claude-code) que convierte una idea en un
**carrusel de Instagram listo para publicar**: escribe el copy, genera las imágenes con tu
marca y las sube a Instagram por ti.

Le hablas normal ("hazme un carrusel sobre X") o escribes `/carrusel`, respondes unas preguntas,
y listo.

**Es para** creadores y dueños de negocio que quieren publicar carruseles consistentes con su
marca, rápido.

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

Esto copia la skill a `~/.claude/skills/carrusel/` y le prepara su entorno de Python (`venv/`, con `requirements.txt`). Abre Claude Code y escribe `/carrusel`
(o simplemente pídele un carrusel). La skill te guía en el resto, incluido sacar las llaves.

## Qué cuesta

La skill es **gratis**. Para usarla necesitas:
- **Claude Code** (plan Pro).
- **Kie AI** para las imágenes — ~**$0.10 USD por slide** (un carrusel de 6 ≈ $0.60).
- **Upload Post** para publicar — **gratis** hasta 10 publicaciones al mes (sin tarjeta).

Es normal pagar los servicios que uno usa; la skill te guía para conseguir cada llave.

## Requisito para publicar en Instagram

Instagram solo permite publicar por API desde cuentas **Business o Creator** ligadas a una
página de Facebook (requisito de Meta). La skill te acompaña a dejarlo listo.

## Cómo está armado

| Pieza | Qué hace |
|---|---|
| [`SKILL.md`](SKILL.md) | El guion de la skill: onboarding de marca, copy, generación y publicación |
| [`scripts/generar.py`](scripts/generar.py) | Lee tu marca y el copy, y genera las slides en paralelo con Kie AI (nano-banana-pro) |
| [`scripts/publicar.py`](scripts/publicar.py) | Sube el carrusel a Instagram (u otras redes) con Upload Post |
| [`scripts/test_generar.py`](scripts/test_generar.py) | Pruebas unitarias de `generar.py` |
| [`config/marca.example.json`](config/marca.example.json) | Plantilla de tu marca; la skill la llena como `config/marca.json` |
| [`reference/`](reference/) · [`walkthroughs/`](walkthroughs/) | La estructura del carrusel y las guías para sacar cada llave |
| `install.sh` · `install.ps1` | Instaladores para Mac/Linux y Windows |

Tus llaves van en `.env` (plantilla: [`.env.example`](.env.example)), que no se sube a GitHub.

## Uso manual (opcional, para técnicos)

Desde la carpeta de la skill (`~/.claude/skills/carrusel/`), con su entorno activado (`source venv/bin/activate` en Mac/Linux):

```bash
# generar (lee config/marca.json y outputs/<carpeta>/carrusel.md)
python3 scripts/generar.py "outputs/mi-carrusel" --dry-run   # revisar sin gastar
python3 scripts/generar.py "outputs/mi-carrusel"             # generar de verdad

# publicar (por defecto solo en Instagram)
python3 scripts/publicar.py "outputs/mi-carrusel" --caption "..." --dry-run
python3 scripts/publicar.py "outputs/mi-carrusel" --caption "..."

# publicar en varias redes conectadas en Upload Post (opcional)
python3 scripts/publicar.py "outputs/mi-carrusel" --caption "..." --plataformas instagram,tiktok,linkedin
```

> El campo opcional `plataformas` en `config/marca.json` (ej. `["instagram", "tiktok"]`) fija tus
> redes por defecto; `--plataformas` lo sobreescribe. Sin nada, publica solo en Instagram.

## Créditos

Motor de generación inspirado en flujos abiertos de generación de carruseles con Kie AI.
Hecho para publicar contenido consistente, rápido.
