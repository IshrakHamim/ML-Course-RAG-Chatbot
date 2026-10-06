import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { deleteAllSessions, deleteSession, getSession, listSessions } from '../api/chat'
import { ApiError } from '../api/client'
import type { SessionSummary } from '../api/types'
import { ChatWindow } from '../components/ChatWindow'
import { toView, type ChatMessageView } from '../components/chatTypes'
import { ErrorBanner } from '../components/ErrorBanner'
import { SessionList } from '../components/SessionList'
import { Spinner } from '../components/Spinner'

interface LoadedSession {
  // The navigation that fetched these messages. Revisiting a session is a new navigation,
  // so the conversation is refetched instead of showing an outdated copy.
  navigationKey: string
  messages: ChatMessageView[]
}

export function ChatPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const { key: navigationKey } = useLocation()
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loaded, setLoaded] = useState<LoadedSession | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refreshSessions = useCallback(() => {
    listSessions()
      .then(setSessions)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  useEffect(refreshSessions, [refreshSessions])

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    getSession(sessionId)
      .then((detail) => {
        if (!cancelled) setLoaded({ navigationKey, messages: detail.messages.map(toView) })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && (err.status === 404 || err.status === 422)) {
          navigate('/chat', { replace: true })
        } else {
          setError(err instanceof Error ? err.message : String(err))
        }
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, navigationKey, navigate])

  async function handleDelete(id: string) {
    try {
      await deleteSession(id)
      if (id === sessionId) navigate('/chat')
      refreshSessions()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleDeleteAll() {
    if (!window.confirm('Delete all conversations? This cannot be undone.')) return
    try {
      await deleteAllSessions()
      if (sessionId) navigate('/chat')
      refreshSessions()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const ready = !sessionId || loaded?.navigationKey === navigationKey

  return (
    <div className="chat-layout">
      <aside className="sidebar">
        <button type="button" className="primary" onClick={() => navigate('/chat')}>
          + New chat
        </button>
        <SessionList sessions={sessions} onDelete={(id) => void handleDelete(id)} />
        {sessions.length > 0 && (
          <button
            type="button"
            className="danger delete-all"
            onClick={() => void handleDeleteAll()}
          >
            Delete all chats
          </button>
        )}
      </aside>
      <div className="chat-main">
        {error && <ErrorBanner message={error} onRetry={() => window.location.reload()} />}
        {ready ? (
          <ChatWindow
            key={sessionId ? navigationKey : 'new'}
            sessionId={sessionId}
            initialMessages={sessionId && loaded ? loaded.messages : []}
            onSessionCreated={(id) => navigate(`/chat/${id}`)}
            onAnswered={refreshSessions}
          />
        ) : (
          <div className="page-center">
            <Spinner label="Loading conversation" />
          </div>
        )}
      </div>
    </div>
  )
}
