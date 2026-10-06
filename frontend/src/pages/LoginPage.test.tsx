import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { AuthContext, type AuthState } from '../auth/AuthContext'
import { LoginPage } from './LoginPage'

function renderLogin(overrides: Partial<AuthState> = {}) {
  const value: AuthState = {
    user: null,
    loading: false,
    login: vi.fn().mockResolvedValue(undefined),
    register: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn(),
    ...overrides,
  }
  render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/chat" element={<p>chat page</p>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
  return value
}

async function fillAndSubmit(email: string, password: string, button = /log in/i) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/email/i), email)
  await user.type(screen.getByLabelText(/password/i), password)
  await user.click(screen.getByRole('button', { name: button }))
}

describe('LoginPage', () => {
  it('shows the QueryBuddy name', () => {
    renderLogin()
    expect(screen.getByRole('heading', { name: 'QueryBuddy' })).toBeInTheDocument()
  })

  it('logs in and goes to the chat', async () => {
    const auth = renderLogin()
    await fillAndSubmit('amy@example.com', 'password123')
    expect(auth.login).toHaveBeenCalledWith('amy@example.com', 'password123')
    expect(await screen.findByText('chat page')).toBeInTheDocument()
  })

  it('shows server error and keeps inputs', async () => {
    renderLogin({
      login: vi.fn().mockRejectedValue(new ApiError(401, 'Invalid email or password')),
    })
    await fillAndSubmit('amy@example.com', 'wrongpass1')
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
    expect(screen.getByLabelText(/email/i)).toHaveValue('amy@example.com')
  })

  it('blocks submit for password under 8 chars', async () => {
    const auth = renderLogin()
    await fillAndSubmit('amy@example.com', 'short')
    expect(auth.login).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('at least 8 characters')
  })

  it('can switch to registration', async () => {
    const auth = renderLogin()
    await userEvent.setup().click(screen.getByRole('button', { name: /create an account/i }))
    await fillAndSubmit('new@example.com', 'password123', /register/i)
    expect(auth.register).toHaveBeenCalledWith('new@example.com', 'password123')
  })
})
