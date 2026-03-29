/**
 * Copy Vite dist/ into jvspatial/static/admin_graph (inside the jvspatial package).
 * Run from jvgraph-ui: npm run embed
 */
const fs = require('fs')
const path = require('path')

const root = path.resolve(__dirname, '..')
const dist = path.join(root, 'dist')
const target = path.join(root, '..', 'jvspatial', 'static', 'admin_graph')

if (!fs.existsSync(dist)) {
  console.error('dist/ missing — run npm run build:embed first')
  process.exit(1)
}

fs.rmSync(target, { recursive: true, force: true })
fs.mkdirSync(target, { recursive: true })
fs.cpSync(dist, target, { recursive: true })
console.log('Embedded admin graph UI →', target)
