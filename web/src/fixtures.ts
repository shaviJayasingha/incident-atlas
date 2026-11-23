import scenariosJson from '../../data/incidents/scenarios.json'
import replaysJson from '../../data/incidents/replays.json'
import type {
  DependenciesResponse,
  EvidenceItemOut,
  IncidentAtlasClient,
  HypothesisOut,
  IncidentCard,
  IncidentDetail,
  InvestigationReport,
  LogEventOut,
  MetricPointOut,
  SpanOut,
  TelemetryKind,
  TimelineEventOut,
  ApprovalCreate,
  ApprovalResponse,
  DemoCapabilities,
  InvestigationCreate,
  Source,
} from './contracts'

type Scenario = (typeof scenariosJson.scenarios)[number]
type Replay = (typeof replaysJson.reports)[number]
const FIXTURE_VERSION = scenariosJson.fixture_version
const fixtureApprovals = new Map<string, ApprovalResponse>()
const fixtureApprovalKey = (reportId: string, mitigationId: string) => `incident-atlas:fixture-approval:${reportId}:${mitigationId}`
const snapshots: Record<string, { id: string; sha: string }> = {
  'inc-cache-collapse-001': { id: 'snap-inc-cache-collapse-001-1.0.0', sha: '7d09c04c3856d9fcc5e1c9b1a07581bbe5447e162d85dca700c7aa139d55d15d' },
  'inc-inventory-pool-002': { id: 'snap-inc-inventory-pool-002-1.0.0', sha: '7ee8b70c152ea0e654758c62c7146b7b0df646f6c9c8cd0a717b59e5bd13f75d' },
  'inc-payment-gateway-003': { id: 'snap-inc-payment-gateway-003-1.0.0', sha: 'a15f0a87598bd002d7123600578911f98e84087d3eca35e6be4cb0256ab92ed6' },
}
const iso = (base: string, minutes: number) => new Date(Date.parse(base) + minutes * 60_000).toISOString().replace('.000Z', 'Z')

const evidenceFor = (scenario: Scenario): EvidenceItemOut[] => {
  const snapshot = snapshots[scenario.id]
  const items: EvidenceItemOut[] = []
  for (const event of scenario.timeline) {
    const payload = { title: event.title, summary: event.summary, kind: event.kind, attributes: event.attributes ?? {} }
    items.push({ evidence_id: event.id, kind: 'timeline', source_record_id: event.id, service_id: event.service_id ?? null, observed_at: iso(scenario.started_at, event.offset_minutes), fixture_version: FIXTURE_VERSION, payload, snapshot_id: snapshot.id, snapshot_sha256: snapshot.sha })
  }
  for (const series of scenario.metrics) {
    const anchors = (series.evidence_ids ?? {}) as Record<string, string>
    series.values.forEach((value, index) => {
      const evidenceId = anchors[String(index)] ?? `ev-${series.series_id}-${String(index).padStart(2, '0')}`
      items.push({ evidence_id: evidenceId, kind: 'metric', source_record_id: evidenceId, service_id: series.service_id, observed_at: iso(scenario.started_at, index - 5), fixture_version: FIXTURE_VERSION, payload: { series_id: series.series_id, metric_name: series.metric_name, value: Number(value), unit: series.unit, statistic: series.statistic, labels: series.labels ?? {} }, snapshot_id: snapshot.id, snapshot_sha256: snapshot.sha })
    })
  }
  for (const log of scenario.logs) {
    items.push({ evidence_id: log.id, kind: 'log', source_record_id: log.id, service_id: log.service_id, observed_at: iso(scenario.started_at, log.offset_minutes), fixture_version: FIXTURE_VERSION, payload: { severity: log.severity, message: log.body, trace_id: log.trace_id ?? null, span_id: log.span_id ?? null, attributes: log.attributes ?? {} }, snapshot_id: snapshot.id, snapshot_sha256: snapshot.sha })
  }
  for (const span of scenario.spans) {
    items.push({ evidence_id: span.id, kind: 'span', source_record_id: span.id, service_id: span.service_id, observed_at: iso(scenario.started_at, span.offset_minutes), fixture_version: FIXTURE_VERSION, payload: { trace_id: span.trace_id, span_id: span.span_id, parent_span_id: span.parent_span_id ?? null, operation: span.operation, duration_ms: Number(span.duration_ms), status: span.status, attributes: span.attributes ?? {} }, snapshot_id: snapshot.id, snapshot_sha256: snapshot.sha })
  }
  return items.sort((a, b) => a.observed_at.localeCompare(b.observed_at) || a.evidence_id.localeCompare(b.evidence_id))
}

const cardFor = (scenario: Scenario): IncidentCard => ({ id: scenario.id, title: scenario.title, severity: scenario.severity as IncidentCard['severity'], primary_service: scenario.primary_service_id, started_at: scenario.started_at, ended_at: scenario.ended_at, fixture_version: FIXTURE_VERSION, replay_available: true, symptom_summary: scenario.summary })
const detailFor = (scenario: Scenario): IncidentDetail => ({ ...cardFor(scenario), slug: scenario.slug, scenario_seed: scenario.scenario_seed, display_timezone: 'UTC', services: [...scenario.services].sort((a, b) => a.id.localeCompare(b.id)).map(service => ({ ...service, attributes: service.attributes ?? {} })) })
const timelineFor = (scenario: Scenario): TimelineEventOut[] => scenario.timeline.map(event => ({ evidence_id: event.id, occurred_at: iso(scenario.started_at, event.offset_minutes), kind: event.kind, service_id: event.service_id ?? null, title: event.title, summary: event.summary, source_record_id: event.source_record_id ?? null, fixture_version: FIXTURE_VERSION, attributes: event.attributes ?? {} })).sort((a, b) => a.occurred_at.localeCompare(b.occurred_at) || a.evidence_id.localeCompare(b.evidence_id))
const dependenciesFor = (scenario: Scenario): DependenciesResponse => ({
  nodes: scenario.services.map(service => ({ id: service.id, name: service.name, tier: service.tier, team: service.team, role: scenario.incident_services.find(item => item.service_id === service.id)?.role ?? 'dependency' })),
  edges: scenario.dependencies.map(edge => ({ ...edge, relationship: 'calls', observed: true, attributes: {} })),
  request_id: `fixture-${scenario.id}-dependencies`,
})
const telemetryFor = (scenario: Scenario, kind: TelemetryKind): MetricPointOut[] | LogEventOut[] | SpanOut[] => {
  if (kind === 'metrics') return scenario.metrics.flatMap(series => series.values.map((value, index) => ({ evidence_id: (series.evidence_ids as Record<string, string> | undefined)?.[String(index)] ?? `ev-${series.series_id}-${String(index).padStart(2, '0')}`, kind: 'metric' as const, series_id: series.series_id, metric_name: series.metric_name, service_id: series.service_id, observed_at: iso(scenario.started_at, index - 5), value: Number(value), unit: series.unit, statistic: series.statistic, labels: series.labels ?? {}, fixture_version: FIXTURE_VERSION }))).sort((a, b) => a.observed_at.localeCompare(b.observed_at) || a.evidence_id.localeCompare(b.evidence_id))
  if (kind === 'logs') return scenario.logs.map(log => ({ evidence_id: log.id, kind: 'log' as const, observed_at: iso(scenario.started_at, log.offset_minutes), severity: log.severity, service_id: log.service_id, message: log.body, trace_id: log.trace_id ?? null, span_id: log.span_id ?? null, attributes: log.attributes ?? {}, fixture_version: FIXTURE_VERSION })).sort((a, b) => a.observed_at.localeCompare(b.observed_at) || a.evidence_id.localeCompare(b.evidence_id))
  return scenario.spans.map(span => ({ evidence_id: span.id, kind: 'span' as const, trace_id: span.trace_id, span_id: span.span_id, parent_span_id: span.parent_span_id ?? null, service_id: span.service_id, operation: span.operation, started_at: iso(scenario.started_at, span.offset_minutes), duration_ms: Number(span.duration_ms), status: span.status, attributes: span.attributes ?? {}, fixture_version: FIXTURE_VERSION })).sort((a, b) => a.started_at.localeCompare(b.started_at) || a.evidence_id.localeCompare(b.evidence_id))
}
const replayFor = (replay: Replay): InvestigationReport => {
  const snapshot = snapshots[replay.incident_id]
  const scenario = scenariosJson.scenarios.find(item => item.id === replay.incident_id)
  const hypotheses: HypothesisOut[] = replay.hypotheses.map(hypothesis => ({ id: hypothesis.id, rank: hypothesis.rank, statement: hypothesis.statement, confidence: 'high', confidence_note: hypothesis.confidence_note, supporting_evidence_ids: hypothesis.supporting_evidence_ids, contradicting_evidence_ids: hypothesis.contradicting_evidence_ids, next_read_only_check: hypothesis.next_read_only_check, mitigation: { id: hypothesis.mitigation_id, summary: hypothesis.mitigation_summary, simulation_only: true } }))
  return { id: replay.id, incident_id: replay.incident_id, fixture_version: FIXTURE_VERSION, source: 'stored_replay', model_call_made: false, status: 'completed', started_at: scenario?.started_at ?? replay.created_at, completed_at: replay.created_at, model_id: 'curated-fixture', prompt_version: 'curated-replay-v1', schema_version: 'investigation-report-v1', evidence_snapshot_id: snapshot.id, evidence_snapshot_sha256: snapshot.sha, uncertainty: replay.uncertainty, hypotheses, rules_baseline: replay.rules_baseline, usage: { input_tokens: 0, output_tokens: 0 }, trace_id: null, replay_id: replay.id, originally_generated_at: replay.created_at, request_id: `fixture-${replay.id}` }
}

export const fixtureClient: IncidentAtlasClient = {
  mode: 'fixtures',
  getCapabilities: async (): Promise<DemoCapabilities> => ({ stored_replay_available: true, live_ai_enabled: false, live_label: 'Live analysis is unavailable in fixture preview.', rate_limit: 'Development fixture preview; no API request.', request_id: 'fixture-capabilities' }),
  listIncidents: async () => scenariosJson.scenarios.map(cardFor),
  getIncident: async id => { const item = scenariosJson.scenarios.find(scenario => scenario.id === id); return item ? detailFor(item) : undefined },
  getTimeline: async id => { const item = scenariosJson.scenarios.find(scenario => scenario.id === id); return item ? timelineFor(item) : [] },
  getDependencies: async id => { const item = scenariosJson.scenarios.find(scenario => scenario.id === id); return item ? dependenciesFor(item) : undefined },
  getTelemetry: async (id, kind) => { const item = scenariosJson.scenarios.find(scenario => scenario.id === id); return item ? telemetryFor(item, kind) : [] },
  getReplay: async id => { const item = replaysJson.reports.find(replay => replay.id === id || replay.incident_id === id); return item ? replayFor(item) : undefined },
  getReport: async (id, source: Source) => source === 'stored_replay' ? fixtureClient.getReplay(id) : undefined,
  getEvidence: async (incidentId, evidenceId, snapshotId) => { const scenario = scenariosJson.scenarios.find(item => item.id === incidentId); const item = scenario ? evidenceFor(scenario).find(evidence => evidence.evidence_id === evidenceId) : undefined; return item && (!snapshotId || item.snapshot_id === snapshotId) ? item : undefined },
  createInvestigation: async (_body: InvestigationCreate) => { throw new Error('Live investigations are unavailable in fixture preview.') },
  getApproval: async (report, mitigationId) => {
    const key = fixtureApprovalKey(report.id, mitigationId)
    try {
      const saved = window.localStorage.getItem(key)
      if (saved) return JSON.parse(saved) as ApprovalResponse
    } catch { /* local-only fallback for storage-restricted previews */ }
    return fixtureApprovals.get(key) ?? null
  },
  approve: async (report: InvestigationReport, body: ApprovalCreate): Promise<ApprovalResponse> => {
    if (!body.simulation_acknowledged) throw new Error('Explicit simulation acknowledgment is required.')
    const approval = { id: `fixture-approval-${crypto.randomUUID()}`, investigation_id: report.source === 'live_ai' ? report.id : null, replay_id: report.source === 'stored_replay' ? report.replay_id ?? report.id : null, mitigation_id: body.mitigation_id, status: 'simulated_approved', simulation_only: true, external_action_performed: false, recorded_at: new Date().toISOString(), message: 'Simulation recorded; no system was changed.', request_id: 'fixture-approval-local' } as const
    const key = fixtureApprovalKey(report.id, body.mitigation_id)
    fixtureApprovals.set(key, approval)
    try { window.localStorage.setItem(key, JSON.stringify(approval)) } catch { /* local-only fallback for storage-restricted previews */ }
    return approval
  },
}

export const incidentTitle = async (incidentId: string) => (await fixtureClient.getIncident(incidentId))?.title ?? 'Unknown incident'
export const reportById = (reportId: string) => fixtureClient.getReplay(reportId)
export const reportsForFixtures = (replaysJson.reports as Replay[]).map(replayFor)
