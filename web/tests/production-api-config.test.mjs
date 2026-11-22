import assert from 'node:assert/strict'
import test from 'node:test'
import { validateProductionApiBase } from '../scripts/production-api-config.mjs'

test('production API URL requires an absolute HTTPS /api/v1 endpoint', () => {
  assert.equal(
    validateProductionApiBase('https://incident-api.example.com/api/v1'),
    'https://incident-api.example.com/api/v1',
  )
})

test('production API URL rejects missing, relative, plaintext, and wrong-path values', () => {
  for (const value of [undefined, '', '/api/v1', 'http://api.example.com/api/v1', 'https://site.netlify.app/']) {
    assert.throws(() => validateProductionApiBase(value))
  }
})

test('production API URL rejects credentials and query strings', () => {
  assert.throws(() => validateProductionApiBase('https://user:secret@api.example.com/api/v1'))
  assert.throws(() => validateProductionApiBase('https://api.example.com/api/v1?key=value'))
})
