import type { DemoCapabilities } from './contracts'
import type { Resource } from './useResource'

export function canRunLiveInvestigation(mode: 'api' | 'fixtures', capability: Resource<DemoCapabilities>) {
  return mode === 'api' && capability.status === 'ready' && capability.data.live_ai_enabled
}

export function evidenceLinkPath(incidentId: string, snapshotId: string, evidenceId: string) {
  const query = new URLSearchParams({ evidence: evidenceId, snapshot: snapshotId })
  return `/incidents/${encodeURIComponent(incidentId)}?${query.toString()}`
}

export function reportPath(reportId: string, source: 'live_ai' | 'stored_replay') {
  return `/investigations/${encodeURIComponent(reportId)}?source=${source}`
}
