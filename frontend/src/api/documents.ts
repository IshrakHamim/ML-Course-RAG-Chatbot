import { apiFetch } from './client'
import type { DocumentItem } from './types'

export function listDocuments(): Promise<DocumentItem[]> {
  return apiFetch('/documents')
}

export function uploadDocument(file: File): Promise<DocumentItem> {
  const body = new FormData()
  body.append('file', file)
  // No Content-Type header: the browser sets the multipart boundary itself.
  return apiFetch('/documents', { method: 'POST', body })
}

export function addUrl(url: string): Promise<DocumentItem> {
  return apiFetch('/documents/url', { method: 'POST', json: { url } })
}

export function deleteDocument(id: string): Promise<void> {
  return apiFetch(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
