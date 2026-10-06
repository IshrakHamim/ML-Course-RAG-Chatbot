import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as chatApi from '../api/chat'
import type { Message, SessionDetail } from '../api/types'
import { ChatPage } from './ChatPage'

vi.mock('../api/chat')
const api = vi.mocked(chatApi)

function message(role: Message['role'], content: string): Message {
  return {
    role,
    content,
    sources: [],
    grounded: null,
    kind: null,
    created_at: '2026-10-06T10:00:00Z',
  }
}

const firstExchange = [message('user', 'First question'), message('assistant', 'First answer')]
const secondExchange = [
  message('user', 'Follow-up question'),
  message('assistant', 'Second answer'),
]

function session(messages: Message[]): SessionDetail {
  return { id: 'A', title: 'First question', messages }
}

function renderPage(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        {['/chat', '/chat/:sessionId'].map((routePath) => (
          <Route key={routePath} path={routePath} element={<ChatPage />} />
        ))}
      </Routes>
    </MemoryRouter>,
  )
}

describe('ChatPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.listSessions.mockResolvedValue([
      { id: 'A', title: 'First question', created_at: '', updated_at: '' },
    ])
  })

  it('shows the latest messages when returning to a conversation', async () => {
    api.getSession
      .mockResolvedValueOnce(session(firstExchange))
      .mockResolvedValueOnce(session([...firstExchange, ...secondExchange]))
    const user = userEvent.setup()
    renderPage('/chat/A')
    expect(await screen.findByText('First answer')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /new chat/i }))
    expect(screen.queryByText('First answer')).not.toBeInTheDocument()

    await user.click(screen.getByRole('link', { name: 'First question' }))
    expect(await screen.findByText('Second answer')).toBeInTheDocument()
    expect(api.getSession).toHaveBeenCalledTimes(2)
  })

  it('goes back to a new chat when the session no longer exists', async () => {
    const { ApiError } = await import('../api/client')
    api.getSession.mockRejectedValue(new ApiError(404, 'Session not found'))
    renderPage('/chat/missing')
    expect(await screen.findByText('Ask anything from the knowledge base.')).toBeInTheDocument()
  })
})

describe('ChatPage delete all', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('deletes every conversation after confirmation', async () => {
    api.listSessions
      .mockResolvedValueOnce([
        { id: 'A', title: 'First question', created_at: '', updated_at: '' },
        { id: 'B', title: 'Second question', created_at: '', updated_at: '' },
      ])
      .mockResolvedValue([])
    api.deleteAllSessions.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderPage('/chat')

    await user.click(await screen.findByRole('button', { name: /delete all chats/i }))
    expect(api.deleteAllSessions).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('No conversations yet.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /delete all chats/i })).not.toBeInTheDocument()
  })

  it('keeps conversations when the confirmation is cancelled', async () => {
    api.listSessions.mockResolvedValue([
      { id: 'A', title: 'First question', created_at: '', updated_at: '' },
    ])
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderPage('/chat')

    await user.click(await screen.findByRole('button', { name: /delete all chats/i }))
    expect(api.deleteAllSessions).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'First question' })).toBeInTheDocument()
  })
})
