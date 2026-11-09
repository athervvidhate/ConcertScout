// Where the browser tests run. Set E2E_WEB_PORT and E2E_API_PORT to run beside another checkout's
// tests; `npm run build:e2e` reads the same variables, so build and test with the same values.
export const WEB_URL = `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? "3146"}`;
export const API_PORT = process.env.E2E_API_PORT ?? "8146";
export const API_URL = `http://127.0.0.1:${API_PORT}`;
