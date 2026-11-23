import { pathToFileURL } from 'node:url'
import { isIP } from 'node:net'

function isReservedOrNonPublicHost(hostname) {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, '').replace(/\.$/, '')
  if (
    host === 'localhost' ||
    host.endsWith('.localhost') ||
    host.endsWith('.local') ||
    host.endsWith('.internal') ||
    host.endsWith('.lan') ||
    host.endsWith('.invalid') ||
    host === 'invalid' ||
    host.endsWith('.test') ||
    host === 'test' ||
    host.endsWith('.example') ||
    host === 'example' ||
    ['example.com', 'example.net', 'example.org'].some(
      (reserved) => host === reserved || host.endsWith(`.${reserved}`),
    )
  ) {
    return true
  }

  const address = host
  if (isIP(address) === 4) {
    const octets = address.split('.').map(Number)
    const [a, b] = octets
    return (
      a === 0 ||
      a === 10 ||
      a === 127 ||
      (a === 100 && b >= 64 && b <= 127) ||
      (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) ||
      (a === 192 && (b === 168 || (b === 0 && (octets[2] === 0 || octets[2] === 2)))) ||
      (a === 198 && (b === 18 || b === 19 || (b === 51 && octets[2] === 100))) ||
      (a === 203 && b === 0 && octets[2] === 113) ||
      a >= 224
    )
  }
  if (isIP(address) === 6) {
    return (
      address === '::' ||
      address === '::1' ||
      address.startsWith('fc') ||
      address.startsWith('fd') ||
      address.startsWith('fe8') ||
      address.startsWith('fe9') ||
      address.startsWith('fea') ||
      address.startsWith('feb') ||
      address.startsWith('2001:db8:')
    )
  }
  return false
}

export function validateProductionApiBase(
  value,
  { allowCiPlaceholder = process.env.CI === 'true' && process.env.INCIDENT_ATLAS_CI === 'true' } = {},
) {
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
  if (!allowCiPlaceholder && isReservedOrNonPublicHost(url.hostname)) {
    throw new Error('VITE_API_BASE_URL must use a public, non-reserved production API hostname.')
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
