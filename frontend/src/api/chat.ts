import { apiFetch } from './client'
import type { ChatResponse, SessionDetail, SessionSummary } from './types'

export function sendMessage(message: string, sessionId?: string): Promise<ChatResponse> {
  return apiFetch('/chat', { method: 'POST', json: { message, session_id: sessionId } })
}

export function listSessions(): Promise<SessionSummary[]> {
  return apiFetch('/chat/sessions')
}

export function getSession(id: string): Promise<SessionDetail> {
  return apiFetch(`/chat/sessions/${encodeURIComponent(id)}`)
}

export function deleteSession(id: string): Promise<void> {
  return apiFetch(`/chat/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function deleteAllSessions(): Promise<void> {
  return apiFetch('/chat/sessions', { method: 'DELETE' })
}
