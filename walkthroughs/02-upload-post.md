# Llave de Upload Post (publica en Instagram)

Upload Post es el servicio que publica el carrusel en tu Instagram por ti.
Tiene un plan **gratis: 10 publicaciones al mes, sin tarjeta**. Suficiente para arrancar.

> Con esta llave la skill **publica en tu Instagram por ti**. Vamos a dejarla lista — es gratis
> (10 publicaciones al mes, sin tarjeta) y rápido.

## Requisito importante de Instagram (dilo antes de empezar)

> Para que se pueda publicar por API, tu cuenta de Instagram tiene que ser **Business o
> Creator** y estar **vinculada a una página de Facebook**. Esto es un requisito de Meta,
> no de nosotros. Si tu cuenta es personal, cámbiala a Creator (es gratis, desde la
> configuración de Instagram) y vincúlala a una página de Facebook.

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
