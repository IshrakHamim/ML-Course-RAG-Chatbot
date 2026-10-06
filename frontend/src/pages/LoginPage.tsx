import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Spinner } from '../components/Spinner'

const MIN_PASSWORD = 8

export function LoginPage() {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const isLogin = mode === 'login'

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (password.length < MIN_PASSWORD) {
      setError(`Password must be at least ${MIN_PASSWORD} characters.`)
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await (isLogin ? login : register)(email.trim(), password)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from && from !== '/login' ? from : '/chat', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
      setSubmitting(false)
    }
  }

  return (
    <main className="page-center">
      <form className="card auth-card" onSubmit={handleSubmit} noValidate>
        <h1>Course Assistant</h1>
        <p className="muted">
          {isLogin ? 'Log in to ask questions about the course material.' : 'Create an account.'}
        </p>
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete={isLogin ? 'current-password' : 'new-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? <Spinner label="Submitting" /> : isLogin ? 'Log in' : 'Register'}
        </button>
        <button
          type="button"
          className="link"
          onClick={() => {
            setMode(isLogin ? 'register' : 'login')
            setError(null)
          }}
        >
          {isLogin ? 'Create an account' : 'I already have an account'}
        </button>
      </form>
    </main>
  )
}
