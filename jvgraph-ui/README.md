# jvgraph-ui

Standalone **Node/npm** admin graph viewer for [jvspatial](https://github.com/TrueSelph/jvspatial): sign in as **admin**, load a progressive subgraph, expand nodes, and inspect the object graph in the browser.

## Optional for most developers

You **do not** need this folder to run or develop jvspatial itself. Use it when you want local UI development with hot reload, or when you need to refresh the embedded static files that ship with the `jvspatial` package.

- **Local graph UI** — `npm run dev` against a jvspatial API on another origin or port.
- **Embedded admin graph** — after `npm run embed`, static files live under `jvspatial/static/admin_graph/` inside the repo; jvspatial serves them at `/admin/graph/` when `graph_endpoint_enabled` is true (reinstall or use an editable install of jvspatial so the package sees the files).

---

## Run the UI with npm (optional)

From this directory:

```bash
cd jvgraph-ui
npm install
npm run dev
```

Open the URL Vite prints (usually `http://127.0.0.1:5173`).

### Connecting to the API

On the login screen:

- **API URL** — origin for all `/api/...` calls: full URL or host with optional port (e.g. `http://127.0.0.1:8000`, `127.0.0.1:8000`, `https://api.example.com`). Scheme defaults to `http` when omitted; path is ignored (only the origin is used).
- **Use same origin as this page** — use relative `/api/...` when the UI is served from the same host as jvspatial (e.g. `/admin/graph/` embed).

Settings are stored in `localStorage`. The browser calls the API **directly** (no Vite proxy). Ensure jvspatial **CORS** allows this page’s origin (e.g. `http://127.0.0.1:5173` and `http://localhost:5173` appear in default `CORSConfig` in `jvspatial/api/config_groups.py`).

Optional env when no saved URL exists: `VITE_DEFAULT_API_BASE`.

---

## Embed static files into jvspatial

Run this after changing the frontend when you need assets inside the Python package:

```bash
npm run embed
```

This runs `build:embed` (asset base `/admin/graph/`) and copies `dist/` into **`jvspatial/static/admin_graph/`** at the repo root. Rebuild or reinstall `jvspatial` so wheels/sdists include those files (they are gitignored except this README under `admin_graph`).

---

## Cross-origin (CORS)

If the UI origin differs from jvspatial, configure CORS on the server (allowed origins + `Authorization`). See `CORSConfig` in `jvspatial/api/config_groups.py` and `jvspatial/api/middleware/manager.py`.

---

## npm scripts

| Script | Purpose |
|--------|---------|
| `npm run dev` | Vite dev server |
| `npm run typecheck` | `tsc --noEmit` (no build output) |
| `npm run build` | Typecheck + production build (asset base `/`) |
| `npm run build:embed` | Typecheck + build for `/admin/graph/` mount |
| `npm run embed` | `build:embed` + copy to `jvspatial/static/admin_graph/` |
| `npm run preview` | Preview production build locally |
