# Solución de problemas

Traduce siempre el error a lenguaje simple. Aquí los más comunes.

## Generación de imágenes (Kie AI)

**"Falta la llave de Kie AI"**
No está `KIE_API_KEY` en el `.env` de la skill. Revisa el walkthrough 01. Confirma que el
`.env` está en la raíz de la skill (junto a `SKILL.md`), no dentro de `scripts/`.

**"No se creó ninguna tarea / revisa tus créditos"**
La llave es válida pero no hay saldo en Kie AI, o la llave está mal copiada. Carga saldo
(con $5 sobra) o vuelve a copiar la llave completa.

**El texto de las imágenes sale con errores de ortografía o cortado**
Los modelos de imagen a veces fallan el texto. Opciones: (1) regenera solo esa lámina con
`--regenerar "N"`; (2) acorta el texto de esa lámina en `carrusel.md`; (3) sube el contraste
en `marca.json`. Menos texto por lámina = mejor resultado.

**"ModuleNotFoundError: No module named 'requests'" (o 'dotenv')**
Falta el entorno de la skill. Créalo/repáralo y corre los scripts con SU python:
```
python3 -m venv ~/.claude/skills/carrusel/venv
~/.claude/skills/carrusel/venv/bin/pip install -r ~/.claude/skills/carrusel/requirements.txt
```
Luego usa `~/.claude/skills/carrusel/venv/bin/python` para correr `generar.py`/`publicar.py`.

## Publicación (Upload Post)

**La publicación falla**
Casi siempre es una de tres:
1. Tu Instagram no es Business/Creator ligada a una página de Facebook (requisito de Meta).
2. El perfil no está conectado en el panel de Upload Post ("Manage Users" → Connect).
3. La llave o el nombre del perfil (`upload_post_user`) están mal.

**"Falta UPLOAD_POST_API_KEY"**
Aún no has conectado Upload Post (walkthrough 02). La generación funciona; para publicar,
seguimos el walkthrough 02 y la dejamos lista.

**Se acabaron mis 10 publicaciones del mes**
Es el límite del plan gratis de Upload Post. Espera al siguiente mes o sube de plan. Mientras,
puedes generar y subir a mano.

## General

**El comando /carrusel no aparece**
Confirma que la skill quedó en `~/.claude/skills/carrusel/` (corre el `install.sh`) y reinicia
Claude Code. También puedes activarla simplemente pidiéndola: "hazme un carrusel sobre X".
