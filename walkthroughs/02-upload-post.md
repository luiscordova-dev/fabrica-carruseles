# Llave de Upload Post (publica en Instagram)

Upload Post es el servicio que publica el carrusel en tu Instagram por ti.
Tiene un plan **gratis: 10 publicaciones al mes, sin tarjeta**. Suficiente para arrancar.

> Con esta llave la skill **publica en tu Instagram por ti**. Vamos a dejarla lista — es gratis
> (10 publicaciones al mes, sin tarjeta) y rápido.

## Requisito importante de Instagram (dilo antes de empezar)

Para publicar por API, la cuenta de Instagram debe ser **Business o Creator** y estar **ligada a
una página de Facebook** (requisito de Meta, no nuestro). Si ya lo tiene, salta esto. Si tiene IG
**personal**, guíala a dejarlo listo — es gratis y toma ~5 minutos:

**Convertir Instagram a Profesional (desde el celular):**
1. Abre Instagram → tu perfil → menú **☰** (arriba a la derecha) → **Configuración y privacidad**.
2. Busca **Tipo de cuenta y herramientas** (o "Cuenta") → **Cambiar a cuenta profesional**.
3. Elige **Creador** o **Empresa** (cualquiera sirve). Elige una categoría y confirma.

**Ligar una página de Facebook:**
1. En ese mismo flujo (o en Configuración → **Compartir en otras apps → Facebook**) te pide
   **conectar una página de Facebook**.
2. Si no tienes una, créala gratis en facebook.com → **Páginas → Crear** (nombre = tu negocio).
3. Conéctala a tu Instagram profesional.

Si en cualquier paso se pierde, **que te mande una captura** y le dices exactamente dónde picar.
Cuando ya sea Business/Creator + página de Facebook, sigan con la llave de Upload Post.

## Guíalo así (paso a paso)

> 1. Entra a **https://upload-post.com** y crea tu cuenta (el plan gratis va bien).
> 2. Busca la sección de **API Keys** y crea una llave. Cópiala completa.
> 3. Pégamela aquí en el chat.
> 4. Ahora hay que **conectar tu Instagram**. Entra a la sección **"Users"** de tu panel
>    (liga directa: **https://app.upload-post.com/manage**) y dale a **Connect** junto a Instagram.
>    Se abre Instagram/Facebook para que aceptes los permisos. Acéptalos todos.
> 5. Cada cuenta conectada tiene un **"Profile"** (un nombre dentro de Upload Post). **Ese Profile es
>    justo lo que necesito para publicar** — y NO es lo mismo que tu @ de Instagram (puede ser tu
>    nombre, `default`, etc.). Dímelo, o mándame una captura de la pantalla "Users" y yo lo saco.

> 💡 **Toma capturas y pásamelas.** En los pasos 4-5: una captura de la pantalla **"Users"**
> (https://app.upload-post.com/manage) me deja ver el nombre exacto del **Profile** **y** a qué
> cuenta de Instagram está conectado — así no publicamos en la cuenta equivocada. Si algo no te
> sale, captura y me la mandas: con eso lo resuelvo.

## Guarda el Profile
Cuando sepas el nombre del Profile, guárdalo en `config/marca.json` como `upload_post_user`. Es lo
que `publicar.py` usa como `--user`. Si te equivocas de cuenta, se corrige cambiando ese valor.

## Cuando el usuario pegue la llave y el perfil
- **NO imprimas la llave** de vuelta.
- Guarda la llave en `.env` como `UPLOAD_POST_API_KEY=`.
- Guarda el nombre del perfil en `config/marca.json`, campo `upload_post_user`.
- Confirma sin mostrar la llave: "Listo, ya puedo publicar en tu Instagram. ✅"

## Verificación (sin publicar nada)
Corre `scripts/publicar.py <carpeta> --caption "prueba" --dry-run`. Muestra el request
exacto que se enviaría y una lista de chequeos (perfil configurado, número de láminas,
llave presente) **sin publicar**. Cuando todo salga en verde, la primera publicación real
la haces cuando tengas un carrusel que te guste.

## Límite del plan gratis
10 publicaciones al mes. Si necesitas más, su plan de pago arranca alrededor de $16/mes.
