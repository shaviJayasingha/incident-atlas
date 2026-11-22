import { pathToFileURL } from 'node:url'

export function validateProductionApiBase(value) {
  if (!value?.trim()) {
    throw new Error('VITE_API_BASE_URL is required for production builds.')
  }

  let url
  try {
    url = new URL(value)
  } catch {
    throw new Error('VITE_API_BASE_URL must be an absolute HTTPS API URL.')
  }

  if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) {
    throw new Error('VITE_API_BASE_URL must use HTTPS and contain no embedded credentials.')
  }
  if (url.pathname.replace(/\/$/, '') !== '/api/v1' || url.search || url.hash) {
    throw new Error('VITE_API_BASE_URL must end with exactly /api/v1 and have no query or fragment.')
  }
  return url.toString().replace(/\/$/, '')
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    validateProductionApiBase(process.env.VITE_API_BASE_URL)
    console.log('Production API URL is an absolute HTTPS /api/v1 endpoint.')
  } catch (error) {
    console.error(error instanceof Error ? error.message : 'Invalid production API URL.')
    process.exitCode = 1
  }
}
