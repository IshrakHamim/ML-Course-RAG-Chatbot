import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { sendMessage } from '../api/chat'
import type { ChatMessageView } from './chatTypes'
import { ErrorBanner } from './ErrorBanner'
import { MessageBubble } from './MessageBubble'
import { Sparkle } from './Sparkle'

export const MAX_MESSAGE_CHARS = 2000

interface ChatWindowProps {
  sessionId?: string
  initialMessages: ChatMessageView[]
  onSessionCreated?: (sessionId: string) => void
  onAnswered?: () => void
}

export function ChatWindow({
  sessionId,
  initialMessages,
  onSessionCreated,
  onAnswered,
}: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessageView[]>(initialMessages)
  const [text, setText] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<{ message: string; text: string } | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const trimmed = text.trim()
  const tooLong = text.length > MAX_MESSAGE_CHARS
  const canSend = !pending && trimmed.length > 0 && !tooLong

  useEffect(() => {
    const list = listRef.current
    if (list) list.scrollTop = list.scrollHeight
  }, [messages, pending])

  async function send(message: string) {
    setError(null)
    setPending(true)
    setText('')
    setMessages((current) => [
      ...current,
      { role: 'user', content: message, sources: [], kind: null },
    ])
    try {
      const response = await sendMessage(message, sessionId)
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: response.answer,
          sources: response.sources,
          kind: response.kind,
        },
      ])
      if (!sessionId) onSessionCreated?.(response.session_id)
      onAnswered?.()
    } catch (err) {
      setMessages((current) => current.slice(0, -1))
      setText(message)
      setError({
        message: err instanceof Error ? err.message : 'Something went wrong.',
        text: message,
      })
    } finally {
      setPending(false)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (canSend) void send(trimmed)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (canSend) void send(trimmed)
    }
  }

  return (
    <section className="chat-window">
      <div className="messages" ref={listRef}>
        {messages.length === 0 && !pending && (
          <div className="empty">
            <h2 className="hello">Hello, I&apos;m QueryBuddy</h2>
            <p className="muted">
              Ask a question about the course material. Answers come only from the knowledge base.
            </p>
          </div>
        )}
        {messages.map((message, index) => (
          <MessageBubble key={index} message={message} />
        ))}
        {pending && (
          <div className="assistant-row">
            <Sparkle className="avatar spinning" />
            <div className="thinking" role="status" aria-label="Thinking">
              <span className="shimmer-text">Thinking…</span>
              <span className="shimmer-bar" />
              <span className="shimmer-bar short" />
            </div>
          </div>
        )}
      </div>
      {error && <ErrorBanner message={error.message} onRetry={() => void send(error.text)} />}
      <form className="composer" data-state={pending ? 'thinking' : 'idle'} onSubmit={handleSubmit}>
        <div className="composer-inner">
          <textarea
            aria-label="Message"
            placeholder="Ask QueryBuddy… (Enter to send, Shift+Enter for a new line)"
            rows={2}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <div className="composer-actions">
            <span className={tooLong ? 'error-text counter' : 'muted counter'}>
              {text.length}/{MAX_MESSAGE_CHARS}
            </span>
            <button type="submit" className="send" disabled={!canSend} aria-label="Send">
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path fill="currentColor" d="M3.4 20.4 21 12 3.4 3.6l-.01 6.53L15 12 3.39 13.87z" />
              </svg>
            </button>
          </div>
        </div>
      </form>
    </section>
  )
}
