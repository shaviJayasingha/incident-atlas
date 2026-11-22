import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiClient, ApiClientError } from '../.test-build/apiClient.js'
import * as ui from '../.test-build/uiContracts.js'

globalThis.window = globalThis

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...headers } })
}

function captureFetch(t, handler) {
  const original = globalThis.fetch
  const calls = []
  globalThis.fetch = async (input, init = {}) => {
    const call = { url: String(input), method: init.method ?? 'GET', headers: new Headers(init.headers), body: init.body, signal: init.signal }
    calls.push(call)
    return handler(call, calls.length)
  }
  t.after(() => { globalThis.fetch = original })
  return calls
}

test('no-key replay journey resolves recorded evidence and persists an acknowledged approval', async t => {
  const incident = { id: 'inc-cache-collapse-001', title: 'Cache collapse', severity: 'SEV-2', primary_service: 'catalog', started_at: '2026-01-15T10:05:00Z', ended_at: '2026-01-15T10:20:00Z', fixture_version: '1.0.0', replay_available: true, symptom_summary: 'Latency rose.' }
  const report = { id: 'replay-cache-v1', replay_id: 'replay-cache-v1', incident_id: incident.id, source: 'stored_replay', model_call_made: false, evidence_snapshot_id: 'snap-cache-v1', evidence_snapshot_sha256: 'f'.repeat(64), fixture_version: '1.0.0', completed_at: '2026-01-15T10:25:00Z', originally_generated_at: '2026-01-15T10:25:00Z', hypotheses: [{ id: 'hyp-1', mitigation: { id: 'mit-1', summary: 'Roll back cache setting.' } }] }
  const evidence = { evidence_id: 'ev-cache-hit-drop', snapshot_id: report.evidence_snapshot_id, snapshot_sha256: report.evidence_snapshot_sha256, kind: 'metric', observed_at: '2026-01-15T10:06:00Z', fixture_version: '1.0.0', source_record_id: 'ev-cache-hit-drop', service_id: 'catalog', payload: { metric_name: 'cache.hit_rate', value: 0.12 } }
  const approval = { id: 'sim-123', replay_id: report.id, investigation_id: null, mitigation_id: 'mit-1', status: 'simulated_approved', simulation_only: true, external_action_performed: false, recorded_at: '2026-01-15T10:26:00Z', message: 'Simulation recorded; no system was changed.', request_id: 'req-approval' }
  const calls = captureFetch(t, (call, n) => {
    const url = new URL(call.url)
    if (url.pathname === '/api/v1/incidents' && n === 1) return json({ items: [incident], next_cursor: 'next-page', request_id: 'req-list-1' })
    if (url.pathname === '/api/v1/incidents' && n === 2) return json({ items: [], next_cursor: null, request_id: 'req-list-2' })
    if (url.pathname === `/api/v1/incidents/${incident.id}`) return json({ ...incident, slug: 'cache-collapse', scenario_seed: 'seed', display_timezone: 'UTC', services: [] })
    if (url.pathname.endsWith('/timeline')) return json({ items: [], next_cursor: null, request_id: 'req-timeline' })
    if (url.pathname.endsWith('/dependencies')) return json({ nodes: [], edges: [], request_id: 'req-dependencies' })
    if (url.pathname.endsWith('/telemetry')) return json({ kind: 'metrics', items: [], next_cursor: null, request_id: 'req-telemetry' })
    if (url.pathname === `/api/v1/incidents/${incident.id}/replay`) return json(report)
    if (url.pathname === `/api/v1/snapshots/${report.evidence_snapshot_id}/evidence/${evidence.evidence_id}`) return json(evidence)
    if (url.pathname === `/api/v1/replays/${report.id}/mitigation-approvals`) return json(approval, 201)
    if (url.pathname === '/api/v1/investigations/inv-live/mitigation-approvals') return json({ ...approval, id: 'sim-live', replay_id: null, investigation_id: 'inv-live' }, 201)
    throw new Error(`Unexpected request: ${call.method} ${url.pathname}`)
  })
  const client = new ApiClient('http://atlas.test/api/v1')

  const incidents = await client.listIncidents()
  assert.equal(incidents.length, 1)
  assert.equal(new URL(calls[1].url).searchParams.get('cursor'), 'next-page')
  assert.equal((await client.getIncident(incident.id)).id, incident.id)
  await client.getTimeline(incident.id)
  await client.getDependencies(incident.id)
  await client.getTelemetry(incident.id, 'metrics')
  const storedReplay = await client.getReplay(incident.id)
  assert.equal(storedReplay.source, 'stored_replay')
  assert.equal(storedReplay.model_call_made, false)
  const resolved = await client.getEvidence(incident.id, evidence.evidence_id, report.evidence_snapshot_id)
  assert.equal(resolved.snapshot_id, report.evidence_snapshot_id)
  await assert.rejects(client.approve(storedReplay, { hypothesis_id: 'hyp-1', mitigation_id: 'mit-1', simulation_acknowledged: false }), /acknowledgment is required/)
  const result = await client.approve(storedReplay, { hypothesis_id: 'hyp-1', mitigation_id: 'mit-1', simulation_acknowledged: true })
  assert.equal(result.simulation_only, true)
  assert.equal(result.external_action_performed, false)
  const approvalCall = calls.at(-1)
  assert.equal(approvalCall.method, 'POST')
  assert.equal(JSON.parse(approvalCall.body).simulation_acknowledged, true)
  assert.match(approvalCall.url, /\/replays\/replay-cache-v1\/mitigation-approvals$/)
  const liveReport = { ...storedReplay, id: 'inv-live', replay_id: null, source: 'live_ai', model_call_made: true }
  const liveApproval = await client.approve(liveReport, { hypothesis_id: 'hyp-1', mitigation_id: 'mit-1', simulation_acknowledged: true })
  assert.equal(liveApproval.investigation_id, 'inv-live')
  assert.equal(calls.at(-1).url, 'http://atlas.test/api/v1/investigations/inv-live/mitigation-approvals')
  assert.equal(calls.some(call => new URL(call.url).pathname === '/api/v1/investigations' && call.method === 'POST'), false, 'stored replay must never create a model run')
  assert.ok(calls.every(call => call.headers.get('Authorization') === null), 'browser sends no model credential')
})

test('live capability gate and live report source remain distinct from replay', async t => {
  const capability = { stored_replay_available: true, live_ai_enabled: false, live_label: 'Disabled by server configuration.', rate_limit: '5 per 15 minutes', request_id: 'req-caps' }
  const enabledCapability = { ...capability, live_ai_enabled: true, request_id: 'req-caps-live' }
  const liveReport = { id: 'inv-1', incident_id: 'inc-cache-collapse-001', source: 'live_ai', model_call_made: true }
  const calls = captureFetch(t, call => {
    const url = new URL(call.url)
    if (url.pathname === '/api/v1/demo-capabilities') return json(calls.length === 1 ? capability : enabledCapability)
    if (url.pathname === '/api/v1/investigations') return json(liveReport, 201)
    if (new URL(call.url).pathname === '/api/v1/investigations/inv-1') return json({ id: 'inv-1', source: 'live_ai', model_call_made: true })
    throw new Error(`Unexpected request: ${call.url}`)
  })
  const client = new ApiClient('http://atlas.test/api/v1')
  const disabled = await client.getCapabilities()
  assert.equal(ui.canRunLiveInvestigation('api', { status: 'ready', data: disabled }), false)
  assert.equal(ui.canRunLiveInvestigation('fixtures', { status: 'ready', data: { ...disabled, live_ai_enabled: true } }), false)
  assert.equal(ui.canRunLiveInvestigation('api', { status: 'loading' }), false)
  assert.equal(calls.length, 1, 'a disabled or unchecked capability state does not enable a live request')
  const enabled = await client.getCapabilities()
  assert.equal(ui.canRunLiveInvestigation('api', { status: 'ready', data: enabled }), true)
  const created = await client.createInvestigation({ incident_id: 'inc-cache-collapse-001', evidence_window_minutes: 15 }, 'live-key-1')
  assert.equal(created.source, 'live_ai')
  assert.equal(calls.at(-1).headers.get('Idempotency-Key'), 'live-key-1')
  const live = await client.getReport('inv-1', 'live_ai')
  assert.equal(live.source, 'live_ai')
  assert.equal(calls.length, 4)
})

test('citation navigation preserves the report snapshot and exact evidence ID', () => {
  const target = ui.evidenceLinkPath('inc/1', 'snap+id', 'ev item/7')
  assert.equal(target, '/incidents/inc%2F1?evidence=ev+item%2F7&snapshot=snap%2Bid')
  assert.equal(ui.reportPath('inv/1', 'live_ai'), '/investigations/inv%2F1?source=live_ai')
})

test('mismatched snapshot evidence and unsafe approval responses are withheld', async t => {
  const calls = captureFetch(t, call => {
    const path = new URL(call.url).pathname
    if (path.endsWith('/evidence/ev-requested')) return json({ evidence_id: 'ev-other', snapshot_id: 'snap-expected' })
    if (path.endsWith('/mitigation-approvals')) return json({ id: 'sim-unsafe', status: 'simulated_approved', simulation_only: true, external_action_performed: true })
    throw new Error(`Unexpected request: ${call.url}`)
  })
  const client = new ApiClient('http://atlas.test/api/v1')
  await assert.rejects(client.getEvidence('inc-1', 'ev-requested', 'snap-expected'), /outside the requested recorded snapshot/)
  const replay = { id: 'replay-1', replay_id: 'replay-1', source: 'stored_replay', model_call_made: false }
  await assert.rejects(client.approve(replay, { hypothesis_id: 'hyp-1', mitigation_id: 'mit-1', simulation_acknowledged: true }), /did not confirm a simulation-only action/)
  assert.equal(calls.length, 2)
})

test('live investigation sends an idempotency key once and surfaces stable invalid-output errors', async t => {
  const problem = { type: 'about:blank', title: 'Bad Gateway', status: 502, code: 'invalid_model_output', detail: 'The live result did not pass validation.', request_id: 'req-invalid', retryable: false }
  const calls = captureFetch(t, () => json(problem, 502, { 'Content-Type': 'application/problem+json' }))
  const client = new ApiClient('http://atlas.test/api/v1')
  await assert.rejects(client.createInvestigation({ incident_id: 'inc-cache-collapse-001', evidence_window_minutes: 15 }, '550e8400-e29b-41d4-a716-446655440000'), error => {
    assert.ok(error instanceof ApiClientError)
    assert.equal(error.code, 'invalid_model_output')
    assert.equal(error.requestId, 'req-invalid')
    return true
  })
  assert.equal(calls.length, 1, 'a failed live POST is not automatically retried')
  assert.equal(calls[0].method, 'POST')
  assert.equal(calls[0].headers.get('Idempotency-Key'), '550e8400-e29b-41d4-a716-446655440000')
  assert.equal(JSON.parse(calls[0].body).incident_id, 'inc-cache-collapse-001')
})

test('safe read retries once on a retryable backend response', async t => {
  const problem = { type: 'about:blank', title: 'Unavailable', status: 503, code: 'database_unavailable', detail: 'Try again.', request_id: 'req-down', retryable: true }
  const calls = captureFetch(t, (_call, count) => count === 1 ? json(problem, 503) : json({ stored_replay_available: true, live_ai_enabled: false, live_label: 'Disabled', rate_limit: 'n/a', request_id: 'req-up' }))
  const capability = await new ApiClient('http://atlas.test/api/v1').getCapabilities()
  assert.equal(capability.request_id, 'req-up')
  assert.equal(calls.length, 2)
})

test('cancelling an API read aborts the underlying fetch', async t => {
  let observedSignal
  captureFetch(t, call => {
    observedSignal = call.signal
    return new Promise((_, reject) => call.signal.addEventListener('abort', () => reject(call.signal.reason), { once: true }))
  })
  const controller = new AbortController()
  const pending = new ApiClient('http://atlas.test/api/v1').getCapabilities(controller.signal)
  await new Promise(resolve => setTimeout(resolve, 0))
  controller.abort()
  await assert.rejects(pending, error => error.name === 'AbortError')
  assert.equal(observedSignal.aborted, true)
})

