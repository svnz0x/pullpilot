# Smoke test: visualizar respuestas con `detail`

## Objetivo
Confirmar que la interfaz web muestra mensajes de error cuando la API responde con un cuerpo `{"detail": "..."}`.

## Preparación
1. Inicia el backend con recarga (por ejemplo):
   ```bash
   uvicorn pullpilot.app:create_app --host 0.0.0.0 --port 8000 --reload
   ```
2. En otra terminal, sirve la UI:
   ```bash
   cd apps/frontend
   npm install
   npm run dev -- --host
   ```
3. Abre `http://localhost:5173/` en el navegador y autentícate con un token válido.

## Pasos
1. Abre las herramientas de desarrollador del navegador y en la pestaña *Network* habilita "Preserve log" para revisar la petición fallida.
2. Envía una petición de guardado con datos inválidos. Una forma sencilla es ejecutar en la consola del navegador:
   ```js
   fetch("http://localhost:8000/api/config", {
     method: "POST",
     headers: {
       Authorization: "Bearer TU_TOKEN_AQUI",
       "Content-Type": "application/json",
     },
     body: JSON.stringify({ detail: "Forzar error de validación" }),
   }).catch(() => {});
   ```
   *(reemplaza `TU_TOKEN_AQUI` por un token válido si no está disponible en memoria).*.
3. Comprueba que la respuesta de la API contiene `{ "detail": "Forzar error de validación" }`.
4. Verifica que la UI muestra "Forzar error de validación" en el banner de estado de configuración.
5. Limpia los estados de error reseteando la configuración desde la UI.

## Resultado esperado
- El banner de estado de configuración cambia a modo error y muestra el texto `Forzar error de validación`.
- No se pierden los resaltados de campos en caso de que la respuesta incluya errores por campo adicionales.
