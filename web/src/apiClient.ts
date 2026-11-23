import type {
  ApprovalCreate,
  ApprovalResponse,
  DemoCapabilities,
  DependenciesResponse,
  EvidenceItemOut,
  IncidentAtlasClient,
  IncidentCard,
  IncidentDetail,
  IncidentListResponse,
  InvestigationCreate,
  InvestigationReport,
  LogEventOut,
  MetricPointOut,
  Problem,
  Source,
  SpanOut,
  TelemetryKind,
  TelemetryResponse,
  TimelineEventOut,
  TimelineResponse,
} from './contracts'

const DEFAULT_BASE = '/api/v1'
const MAX_PAGES = 20
const READ_TIMEOUT_MS = 12_000
const VISITOR_ID_KEY = 'incident-atlas:anonymous-visitor-id'
let volatileVisitorId: string | null = null

function anonymousVisitorId() {
  try {
    const storage = window.localStorage
    const existing = storage.getItem(VISITOR_ID_KEY)
    if (existing && /^[0-9a-f-]{36}$/i.test(existing)) return existing
    const created = window.crypto.randomUUID()
    storage.setItem(VISITOR_ID_KEY, created)
    return created
  } catch {
    // Private browsing restrictions should not block an approval during this tab.
    volatileVisitorId ??= window.crypto?.randomUUID?.() ?? null
    return volatileVisitorId
  }
}

export class ApiClientError extends Error {
  readonly code: string
  readonly status: number
  readonly requestId: string
  readonly retryable: boolean
  readonly retryAfter: string | null

  constructor(problem: Problem, retryAfter: string | null = null) {
    super(problem.detail || problem.title || 'The API request failed.')
    this.name = 'ApiClientError'
    this.code = problem.code
    this.status = problem.status
    this.requestId = problem.request_id
    this.retryable = problem.retryable
    this.retryAfter = retryAfter
  }
}

function abortError(signal?: AbortSignal) {
  return signal?.reason instanceof Error ? signal.reason : new DOMException('The request was cancelled.', 'AbortError')
}

function parseProblem(value: unknown, status: number): Problem {
  if (value && typeof value === 'object') {
    const problem = value as Partial<Problem>
    if (typeof problem.code === 'string') return {
      type: problem.type ?? 'about:blank', title: problem.title ?? 'Request failed', status: problem.status ?? status,
      code: problem.code, detail: problem.detail ?? 'The API request failed.', request_id: problem.request_id ?? 'unknown', retryable: problem.retryable ?? false,
    }
  }
  return { type: 'about:blank', title: 'Request failed', status, code: `http_${status}`, detail: 'The API returned an unreadable error response.', request_id: 'unknown', retryable: status >= 500 }
}

export class ApiClient implements IncidentAtlasClient {
  readonly mode = 'api' as const
  private readonly baseUrl: string

  constructor(baseUrl = import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE) {
    this.baseUrl = baseUrl.replace(/\/$/, '')
  }

  private async request<T>(path: string, options: RequestInit = {}, safeRead = false): Promise<T> {
    const method = options.method ?? 'GET'
    const canRetry = safeRead && method === 'GET'
    let attempt = 0
    while (true) {
      if (options.signal?.aborted) throw abortError(options.signal)
      const controller = new AbortController()
      const forwardAbort = () => controller.abort(options.signal?.reason)
      options.signal?.addEventListener('abort', forwardAbort, { once: true })
      const timer = method === 'GET' ? window.setTimeout(() => controller.abort(new DOMException('The API read timed out.', 'TimeoutError')), READ_TIMEOUT_MS) : undefined
      try {
        const headers = new Headers(options.headers)
        headers.set('Accept', 'application/json, application/problem+json')
        if (path.includes('/mitigation-approvals')) {
          const visitorId = anonymousVisitorId()
          if (visitorId) headers.set('X-Incident-Atlas-Visitor-ID', visitorId)
        }
        const response = await fetch(`${this.baseUrl}${path}`, {
          ...options,
          signal: controller.signal,
          credentials: 'omit',
          headers,
        })
        if (!response.ok) {
          const problem = parseProblem(await response.json().catch(() => undefined), response.status)
          const error = new ApiClientError(problem, response.headers.get('Retry-After'))
          if (canRetry && attempt === 0 && problem.retryable && !options.signal?.aborted) {
            attempt += 1
            const wait = retryDelay(error.retryAfter)
            await delay(wait, options.signal ?? undefined)
            continue
          }
          throw error
        }
        return await response.json() as T
      } catch (error) {
        if (options.signal?.aborted) throw abortError(options.signal)
        if (error instanceof ApiClientError) throw error
        if (canRetry && attempt === 0 && !(error instanceof DOMException && error.name === 'AbortError')) {
          attempt += 1
          await delay(250, options.signal ?? undefined)
          continue
        }
        if (error instanceof Error && error.name === 'AbortError') throw error
        throw error instanceof Error ? error : new Error('The API request failed.')
      } finally {
        if (timer !== undefined) window.clearTimeout(timer)
        options.signal?.removeEventListener('abort', forwardAbort)
      }
    }
  }

  async getCapabilities(signal?: AbortSignal) {
    return this.request<DemoCapabilities>('/demo-capabilities', { signal }, true)
  }

  async listIncidents(signal?: AbortSignal) {
    const items: IncidentCard[] = []
    let cursor: string | null = null
    for (let page = 0; page < MAX_PAGES; page += 1) {
      const query = new URLSearchParams({ limit: '50' })
      if (cursor) query.set('cursor', cursor)
      const response = await this.request<IncidentListResponse>(`/incidents?${query}`, { signal }, true)
      items.push(...response.items)
      cursor = response.next_cursor
      if (!cursor) return items
    }
    throw new Error('The incident catalogue exceeded the client pagination limit.')
  }

  getIncident(id: string, signal?: AbortSignal) {
    return this.request<IncidentDetail>(`/incidents/${encodeURIComponent(id)}`, { signal }, true)
  }

  async getTimeline(id: string, signal?: AbortSignal) {
    const items: TimelineEventOut[] = []
    let cursor: string | null = null
    for (let page = 0; page < MAX_PAGES; page += 1) {
      const query = new URLSearchParams({ limit: '100' })
      if (cursor) query.set('cursor', cursor)
      const response = await this.request<TimelineResponse>(`/incidents/${encodeURIComponent(id)}/timeline?${query}`, { signal }, true)
      items.push(...response.items)
      cursor = response.next_cursor
      if (!cursor) return items
    }
    throw new Error('The incident timeline exceeded the client pagination limit.')
  }

  getDependencies(id: string, signal?: AbortSignal) {
    return this.request<DependenciesResponse>(`/incidents/${encodeURIComponent(id)}/dependencies`, { signal }, true)
  }

  async getTelemetry(id: string, kind: TelemetryKind, signal?: AbortSignal): Promise<MetricPointOut[] | LogEventOut[] | SpanOut[]> {
    const items: Array<MetricPointOut | LogEventOut | SpanOut> = []
    let cursor: string | null = null
    for (let page = 0; page < MAX_PAGES; page += 1) {
      const query = new URLSearchParams({ kind, limit: '200' })
      if (cursor) query.set('cursor', cursor)
      const response = await this.request<TelemetryResponse<MetricPointOut | LogEventOut | SpanOut>>(`/incidents/${encodeURIComponent(id)}/telemetry?${query}`, { signal }, true)
      items.push(...response.items)
      cursor = response.next_cursor
      if (!cursor) return items as MetricPointOut[] | LogEventOut[] | SpanOut[]
    }
    throw new Error(`The ${kind} result exceeded the client pagination limit.`)
  }

  getReplay(id: string, signal?: AbortSignal) {
    return this.request<InvestigationReport>(`/incidents/${encodeURIComponent(id)}/replay`, { signal }, true)
  }

  getReport(id: string, source: Source, signal?: AbortSignal) {
    const path = source === 'stored_replay' ? `/replays/${encodeURIComponent(id)}` : `/investigations/${encodeURIComponent(id)}`
    return this.request<InvestigationReport>(path, { signal }, true)
  }

  async getEvidence(_incidentId: string, evidenceId: string, snapshotId?: string, signal?: AbortSignal) {
    if (!snapshotId) throw new Error('A recorded evidence snapshot is required to resolve a citation.')
    const evidence = await this.request<EvidenceItemOut>(`/snapshots/${encodeURIComponent(snapshotId)}/evidence/${encodeURIComponent(evidenceId)}`, { signal }, true)
    if (evidence.evidence_id !== evidenceId || evidence.snapshot_id !== snapshotId) throw new Error('The API returned evidence outside the requested recorded snapshot. The item was withheld.')
    return evidence
  }

  createInvestigation(body: InvestigationCreate, idempotencyKey: string, signal?: AbortSignal) {
    return this.request<InvestigationReport>('/investigations', {
      method: 'POST', signal,
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(body),
    })
  }

  async getApproval(report: InvestigationReport, mitigationId: string, signal?: AbortSignal) {
    const path = report.source === 'stored_replay'
      ? `/replays/${encodeURIComponent(report.replay_id ?? report.id)}/mitigation-approvals/${encodeURIComponent(mitigationId)}`
      : `/investigations/${encodeURIComponent(report.id)}/mitigation-approvals/${encodeURIComponent(mitigationId)}`
    try {
      return await this.request<ApprovalResponse>(path, { signal }, true)
    } catch (error) {
      if (error instanceof ApiClientError && error.code === 'approval_not_found') return null
      throw error
    }
  }

  async approve(report: InvestigationReport, body: ApprovalCreate, signal?: AbortSignal) {
    if (body.simulation_acknowledged !== true) throw new Error('Explicit simulation acknowledgment is required.')
    const path = report.source === 'stored_replay'
      ? `/replays/${encodeURIComponent(report.replay_id ?? report.id)}/mitigation-approvals`
      : `/investigations/${encodeURIComponent(report.id)}/mitigation-approvals`
    const approval = await this.request<ApprovalResponse>(path, { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (approval.status !== 'simulated_approved' || approval.simulation_only !== true || approval.external_action_performed !== false) throw new Error('The API approval response did not confirm a simulation-only action. No success state was shown.')
    return approval
  }
}

function retryDelay(header: string | null) {
  if (!header) return 250
  const seconds = Number(header)
  if (Number.isFinite(seconds)) return Math.min(Math.max(seconds * 1000, 100), 2_000)
  const date = Date.parse(header)
  return Number.isNaN(date) ? 250 : Math.min(Math.max(date - Date.now(), 100), 2_000)
}

function delay(milliseconds: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(abortError(signal))
    const clearListener = () => signal?.removeEventListener('abort', onAbort)
    const timer = window.setTimeout(() => { clearListener(); resolve() }, milliseconds)
    const onAbort = () => { window.clearTimeout(timer); clearListener(); reject(abortError(signal)) }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}
