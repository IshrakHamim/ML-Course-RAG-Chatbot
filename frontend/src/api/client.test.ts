import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, mockFetch } from '../test/utils'
import { ApiError, apiFetch, getToken, setToken } from './client'

afterEach(() => vi.unstubAllGlobals())

describe('apiFetch', () => {
  it('adds bearer token from sessionStorage', async () => {
    setToken('abc123')
    const fetchMock = mockFetch(jsonResponse({ ok: true }))
    await apiFetch('/auth/me')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/auth/me')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer abc123')
  })

  it('sends JSON bodies with a content type', async () => {
    const fetchMock = mockFetch(jsonResponse({ ok: true }))
    await apiFetch('/chat', { method: 'POST', json: { message: 'hi' } })
    const [, init] = fetchMock.mock.calls[0]
    expect(init.body).toBe('{"message":"hi"}')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('on 401 clears token and dispatches auth:logout', async () => {
    setToken('expired')
    const listener = vi.fn()
    window.addEventListener('auth:logout', listener)
    mockFetch(jsonResponse({ detail: 'Not authenticated' }, 401))
    await expect(apiFetch('/auth/me')).rejects.toMatchObject({ status: 401 })
    expect(getToken()).toBeNull()
    expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener('auth:logout', listener)
  })

  it('uses string detail as error message', async () => {
    mockFetch(jsonResponse({ detail: 'The AI service is busy, please try again.' }, 503))
    const error = await apiFetch('/chat').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(503)
    expect((error as ApiError).message).toBe('The AI service is busy, please try again.')
  })

  it('uses first msg of 422 detail array', async () => {
    mockFetch(
      jsonResponse(
        { detail: [{ loc: ['body', 'message'], msg: 'Value error, Message must not be empty' }] },
        422,
      ),
    )
    await expect(apiFetch('/chat')).rejects.toThrow('Message must not be empty')
  })

  it('falls back to a generic message for non-JSON errors', async () => {
    mockFetch(new Response('<html>Bad gateway</html>', { status: 502 }))
    await expect(apiFetch('/chat')).rejects.toThrow('Request failed (502)')
  })

  it("maps fetch TypeError to status 0 with 'Can't reach the server'", async () => {
    mockFetch(new TypeError('Failed to fetch'))
    const error = (await apiFetch('/health').catch((e: unknown) => e)) as ApiError
    expect(error.status).toBe(0)
    expect(error.message).toContain("Can't reach the server")
  })

  it('returns undefined for 204', async () => {
    mockFetch(new Response(null, { status: 204 }))
    await expect(apiFetch('/chat/sessions/x', { method: 'DELETE' })).resolves.toBeUndefined()
  })
})
