export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

const TOKEN_KEY = 'ragbot.token'
export const LOGOUT_EVENT = 'auth:logout'
const UNREACHABLE_MESSAGE = "Can't reach the server. Is the backend running?"

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Storage unavailable (e.g. private mode); the session lasts until reload.
  }
}

export function clearToken(): void {
  try {
    sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing to clear.
  }
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  json?: unknown
  body?: BodyInit
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json()
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const msg = (detail[0] as { msg?: unknown }).msg
      if (typeof msg === 'string') return msg.replace(/^Value error, /, '')
    }
  } catch {
    // Not JSON; fall through to the generic message.
  }
  return `Request failed (${response.status})`
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { json, headers: initHeaders, ...init } = options
  const headers = new Headers(initHeaders)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let body = init.body
  if (json !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(json)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, body })
  } catch {
    throw new ApiError(0, UNREACHABLE_MESSAGE)
  }

  if (!response.ok) {
    const message = await errorMessage(response)
    if (response.status === 401 && token) {
      clearToken()
      window.dispatchEvent(new Event(LOGOUT_EVENT))
    }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
