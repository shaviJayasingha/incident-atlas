export type Severity = 'SEV-1' | 'SEV-2' | 'SEV-3' | 'SEV-4'
export type Confidence = 'low' | 'medium' | 'high'
export type Source = 'live_ai' | 'stored_replay'
export type TelemetryKind = 'metrics' | 'logs' | 'traces'

export interface IncidentCard {
  id: string
  title: string
  severity: Severity
  primary_service: string
  started_at: string
  ended_at: string
  fixture_version: string
  replay_available: boolean
  symptom_summary: string
}

export interface IncidentListResponse {
  items: IncidentCard[]
  next_cursor: string | null
  request_id: string
}

export interface ServiceOut {
  id: string
  name: string
  tier: string
  team: string
  description: string
  attributes: Record<string, unknown>
}

export interface IncidentDetail extends IncidentCard {
  slug: string
  scenario_seed: string
  display_timezone: string
  services: ServiceOut[]
}

export interface TimelineEventOut {
  evidence_id: string
  occurred_at: string
  kind: string
  service_id: string | null
  title: string
  summary: string
  source_record_id: string | null
  fixture_version: string
  attributes: Record<string, unknown>
}

export interface TimelineResponse {
  items: TimelineEventOut[]
  next_cursor: string | null
  request_id: string
}

export interface DependencyNode {
  id: string
  name: string
  tier: string
  team: string
  role: string
}

export interface DependencyEdgeOut {
  id: string
  from_service_id: string
  to_service_id: string
  relationship: string
  observed: boolean
  attributes: Record<string, unknown>
}

export interface DependenciesResponse {
  nodes: DependencyNode[]
  edges: DependencyEdgeOut[]
  request_id: string
}

export interface MetricPointOut {
  evidence_id: string
  kind: 'metric'
  series_id: string
  metric_name: string
  service_id: string
  observed_at: string
  value: number
  unit: string
  statistic: string
  labels: Record<string, unknown>
  fixture_version: string
}

export interface LogEventOut {
  evidence_id: string
  kind: 'log'
  observed_at: string
  severity: string
  service_id: string
  message: string
  trace_id: string | null
  span_id: string | null
  attributes: Record<string, unknown>
  fixture_version: string
}

export interface SpanOut {
  evidence_id: string
  kind: 'span'
  trace_id: string
  span_id: string
  parent_span_id: string | null
  service_id: string
  operation: string
  started_at: string
  duration_ms: number
  status: string
  attributes: Record<string, unknown>
  fixture_version: string
}

export interface TelemetryResponse<T extends MetricPointOut | LogEventOut | SpanOut> {
  kind: TelemetryKind
  items: T[]
  next_cursor: string | null
  request_id: string
}

export interface EvidenceItemOut {
  evidence_id: string
  kind: string
  source_record_id: string
  service_id: string | null
  observed_at: string
  fixture_version: string
  payload: Record<string, unknown>
  snapshot_id: string
  snapshot_sha256: string
}

export interface MitigationProposal {
  id: string
  summary: string
  simulation_only: true
}

export interface HypothesisOut {
  id: string
  rank: number
  statement: string
  confidence: Confidence
  confidence_note: string
  supporting_evidence_ids: string[]
  contradicting_evidence_ids: string[]
  next_read_only_check: string
  mitigation: MitigationProposal | null
}

export interface RulesBaselineOut {
  version: string
  ranked_labels: string[]
  fired_rules: Array<{ rule_id: string; label: string; evidence_ids: string[] }>
}

export interface InvestigationReport {
  id: string
  incident_id: string
  fixture_version: string
  source: Source
  model_call_made: boolean
  status: string
  started_at: string
  completed_at: string
  model_id: string
  prompt_version: string
  schema_version: string
  evidence_snapshot_id: string
  evidence_snapshot_sha256: string
  uncertainty: string
  hypotheses: HypothesisOut[]
  rules_baseline: RulesBaselineOut
  usage: { input_tokens: number; output_tokens: number }
  trace_id: string | null
  replay_id: string | null
  originally_generated_at: string | null
  request_id: string
}

export interface DemoCapabilities {
  stored_replay_available: boolean
  live_ai_enabled: boolean
  live_label: string
  rate_limit: string
  request_id: string
}

export interface InvestigationCreate {
  incident_id: string
  evidence_window_minutes?: number
}

export interface SnapshotMetadata {
  id: string
  incident_id: string
  fixture_version: string
  created_at: string
  window_start: string
  window_end: string
  sha256: string
  item_count: number
  request_id: string
}

export interface ApprovalCreate {
  hypothesis_id: string
  mitigation_id: string
  simulation_acknowledged: true
}

export interface ApprovalResponse {
  id: string
  investigation_id: string | null
  replay_id: string | null
  mitigation_id: string
  status: 'simulated_approved'
  simulation_only: true
  external_action_performed: false
  recorded_at: string
  message: 'Simulation recorded; no system was changed.'
  request_id: string
}

export interface Problem {
  type: string
  title: string
  status: number
  code: string
  detail: string
  request_id: string
  retryable: boolean
}

export interface IncidentAtlasClient {
  readonly mode: 'api' | 'fixtures'
  getCapabilities(signal?: AbortSignal): Promise<DemoCapabilities>
  listIncidents(signal?: AbortSignal): Promise<IncidentCard[]>
  getIncident(id: string, signal?: AbortSignal): Promise<IncidentDetail | undefined>
  getTimeline(id: string, signal?: AbortSignal): Promise<TimelineEventOut[]>
  getDependencies(id: string, signal?: AbortSignal): Promise<DependenciesResponse | undefined>
  getTelemetry(id: string, kind: TelemetryKind, signal?: AbortSignal): Promise<MetricPointOut[] | LogEventOut[] | SpanOut[]>
  getReplay(id: string, signal?: AbortSignal): Promise<InvestigationReport | undefined>
  getReport(id: string, source: Source, signal?: AbortSignal): Promise<InvestigationReport | undefined>
  getEvidence(incidentId: string, evidenceId: string, snapshotId?: string, signal?: AbortSignal): Promise<EvidenceItemOut | undefined>
  createInvestigation(body: InvestigationCreate, idempotencyKey: string, signal?: AbortSignal): Promise<InvestigationReport>
  getApproval(report: InvestigationReport, mitigationId: string, signal?: AbortSignal): Promise<ApprovalResponse | null>
  approve(report: InvestigationReport, body: ApprovalCreate, signal?: AbortSignal): Promise<ApprovalResponse>
}
