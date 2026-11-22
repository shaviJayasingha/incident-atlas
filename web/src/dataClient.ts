import { ApiClient } from './apiClient'
import type { ApprovalCreate, ApprovalResponse, DemoCapabilities, IncidentAtlasClient, InvestigationCreate, InvestigationReport, Source, TelemetryKind } from './contracts'

const fixturePreviewEnabled = import.meta.env.DEV && import.meta.env.VITE_DATA_MODE === 'fixtures'
export const dataMode: IncidentAtlasClient['mode'] = fixturePreviewEnabled ? 'fixtures' : 'api'
const apiClient = new ApiClient()
let fixtureClientPromise: Promise<IncidentAtlasClient> | undefined

function getClient() {
  if (!fixturePreviewEnabled) return Promise.resolve(apiClient as IncidentAtlasClient)
  fixtureClientPromise ??= import('./fixtures').then(module => module.fixtureClient)
  return fixtureClientPromise
}

export const dataClient: IncidentAtlasClient = {
  mode: dataMode,
  getCapabilities: (signal?: AbortSignal) => getClient().then(client => client.getCapabilities(signal)),
  listIncidents: (signal?: AbortSignal) => getClient().then(client => client.listIncidents(signal)),
  getIncident: (id: string, signal?: AbortSignal) => getClient().then(client => client.getIncident(id, signal)),
  getTimeline: (id: string, signal?: AbortSignal) => getClient().then(client => client.getTimeline(id, signal)),
  getDependencies: (id: string, signal?: AbortSignal) => getClient().then(client => client.getDependencies(id, signal)),
  getTelemetry: (id: string, kind: TelemetryKind, signal?: AbortSignal) => getClient().then(client => client.getTelemetry(id, kind, signal)),
  getReplay: (id: string, signal?: AbortSignal) => getClient().then(client => client.getReplay(id, signal)),
  getReport: (id: string, source: Source, signal?: AbortSignal) => getClient().then(client => client.getReport(id, source, signal)),
  getEvidence: (incidentId: string, evidenceId: string, snapshotId?: string, signal?: AbortSignal) => getClient().then(client => client.getEvidence(incidentId, evidenceId, snapshotId, signal)),
  createInvestigation: (body: InvestigationCreate, key: string, signal?: AbortSignal) => getClient().then(client => client.createInvestigation(body, key, signal)),
  approve: (report: InvestigationReport, body: ApprovalCreate, signal?: AbortSignal): Promise<ApprovalResponse> => getClient().then(client => client.approve(report, body, signal)),
}

export function modeDescription() {
  return dataMode === 'fixtures' ? 'Explicit development fixture preview' : 'Backend API data'
}

export function getDemoCapabilities(signal?: AbortSignal): Promise<DemoCapabilities> {
  return dataClient.getCapabilities(signal)
}
