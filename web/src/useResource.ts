import { useEffect, useState } from 'react'

export type Resource<T> =
  | { status: 'loading'; data?: undefined; error?: undefined }
  | { status: 'error'; data?: undefined; error: Error }
  | { status: 'ready'; data: T; error?: undefined }

type StoredResource<T> = { key: string; status: Resource<T>['status']; data?: T; error?: Error }

export function useResource<T>(key: string, load: (signal: AbortSignal) => Promise<T>) {
  const [attempt, setAttempt] = useState(0)
  const [stored, setStored] = useState<StoredResource<T>>({ key: '', status: 'loading' })
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setStored({ key, status: 'loading' })
    Promise.resolve().then(() => load(controller.signal)).then(data => {
      if (active) setStored({ key, status: 'ready', data })
    }).catch(reason => {
      if (active && !(reason instanceof Error && reason.name === 'AbortError')) setStored({ key, status: 'error', error: reason instanceof Error ? reason : new Error('Request failed') })
    })
    return () => { active = false; controller.abort() }
  }, [key, attempt])
  const resource: Resource<T> = stored.key !== key || stored.status === 'loading'
    ? { status: 'loading' }
    : stored.status === 'error'
      ? { status: 'error', error: stored.error ?? new Error('Request failed') }
      : { status: 'ready', data: stored.data as T }
  return { ...resource, retry: () => setAttempt(value => value + 1) }
}
