import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Sparkle } from './Sparkle'

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          <Sparkle size={22} />
          QueryBuddy
        </span>
        <nav>
          <NavLink to="/chat">Chat</NavLink>
          {user?.role === 'admin' && <NavLink to="/admin">Knowledge base</NavLink>}
        </nav>
        <span className="spacer" />
        <span className="muted user-email">{user?.email}</span>
        <button type="button" className="secondary" onClick={logout}>
          Log out
        </button>
      </header>
      {children}
    </div>
  )
}
