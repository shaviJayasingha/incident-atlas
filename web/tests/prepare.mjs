import { readFile, writeFile } from 'node:fs/promises'

const clientPath = new URL('../.test-build/apiClient.js', import.meta.url)
const compiled = await readFile(clientPath, 'utf8')
await writeFile(clientPath, compiled.replaceAll('import.meta.env.VITE_API_BASE_URL', 'undefined'))
