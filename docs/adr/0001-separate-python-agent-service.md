# Keep the agent in a separate Python service

The agent, external API calls and server-held keys live in a FastAPI service, and Next.js is the web frontend only. A single TypeScript app would cost less and have fewer moving parts, but this project is meant to demonstrate Python AI engineering, and Python has the stronger evaluation tooling. The browser streams directly from the API, so the API owns CORS, bot protection and rate limiting rather than relying on a Next proxy.
