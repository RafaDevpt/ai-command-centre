# Frontend

<!-- Created by Redfox using Claude -->

React 19 + TypeScript + Vite, installable as a PWA. One file per page in
`src/paginas/`; API client with CSRF in `src/api.ts`; dark theme in
`src/index.css`.

```bash
npm ci
npm run dev      # proxies /api to http://127.0.0.1:3000
npm run build    # type-check + production build (served by the backend)
npm run lint     # oxlint
```
