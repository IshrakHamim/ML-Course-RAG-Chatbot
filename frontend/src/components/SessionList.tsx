import { NavLink } from 'react-router-dom'
import type { SessionSummary } from '../api/types'

interface SessionListProps {
  sessions: SessionSummary[]
  onDelete: (id: string) => void
}

export function SessionList({ sessions, onDelete }: SessionListProps) {
  if (sessions.length === 0) return <p className="muted small">No conversations yet.</p>
  return (
    <ul className="session-list" aria-label="Conversations">
      {sessions.map((session) => (
        <li key={session.id}>
          <NavLink to={`/chat/${session.id}`} title={session.title}>
            {session.title}
          </NavLink>
          <button
            type="button"
            className="icon"
            aria-label={`Delete conversation ${session.title}`}
            onClick={() => {
              if (window.confirm('Delete this conversation?')) onDelete(session.id)
            }}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  )
}
