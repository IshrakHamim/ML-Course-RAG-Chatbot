import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { User } from '../api/types'
import { AuthContext, type AuthState } from './AuthContext'
import { RequireAdmin, RequireAuth } from './guards'

function renderAt(path: string, user: User | null, loading = false) {
  const value: AuthState = { user, loading, login: vi.fn(), register: vi.fn(), logout: vi.fn() }
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<p>login page</p>} />
          <Route
            path="/chat"
            element={
              <RequireAuth>
                <p>chat page</p>
              </RequireAuth>
            }
          />
          <Route
            path="/admin"
            element={
              <RequireAdmin>
                <p>admin page</p>
              </RequireAdmin>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

const member: User = { id: '1', email: 'u@example.com', role: 'user' }
const admin: User = { id: '2', email: 'a@example.com', role: 'admin' }

describe('route guards', () => {
  it('RequireAuth redirects anonymous visitors to /login', () => {
    renderAt('/chat', null)
    expect(screen.getByText('login page')).toBeInTheDocument()
  })

  it('RequireAuth shows a loading state while the session is restored', () => {
    renderAt('/chat', null, true)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('RequireAdmin redirects a user-role account to /chat', () => {
    renderAt('/admin', member)
    expect(screen.getByText('chat page')).toBeInTheDocument()
  })

  it('RequireAdmin lets admins in', () => {
    renderAt('/admin', admin)
    expect(screen.getByText('admin page')).toBeInTheDocument()
  })
})
