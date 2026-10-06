import { apiFetch } from './client'
import type { TokenResponse, User } from './types'

export function login(email: string, password: string): Promise<TokenResponse> {
  return apiFetch('/auth/login', { method: 'POST', json: { email, password } })
}

export function register(email: string, password: string): Promise<TokenResponse> {
  return apiFetch('/auth/register', { method: 'POST', json: { email, password } })
}

export function me(): Promise<User> {
  return apiFetch('/auth/me')
}
