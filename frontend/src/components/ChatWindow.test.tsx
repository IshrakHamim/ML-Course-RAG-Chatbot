import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as chatApi from '../api/chat'
import { ApiError } from '../api/client'
import type { ChatResponse } from '../api/types'
import { ChatWindow } from './ChatWindow'

vi.mock('../api/chat')
const sendMessage = vi.mocked(chatApi.sendMessage)

const grounded: ChatResponse = {
  answer: 'Late work loses **10%** per day.',
  sources: [{ title: 'Course Handbook', source_type: 'pdf', page: 3, url: null }],
  session_id: 's1',
  grounded: true,
  kind: 'answer',
}

function setup(props: Partial<Parameters<typeof ChatWindow>[0]> = {}) {
  const onSessionCreated = vi.fn()
  render(<ChatWindow initialMessages={[]} onSessionCreated={onSessionCreated} {...props} />)
  return { user: userEvent.setup(), onSessionCreated }
}

const input = () => screen.getByRole('textbox', { name: /message/i })
const sendButton = () => screen.getByRole('button', { name: /send/i })

describe('ChatWindow', () => {
  beforeEach(() => {
    sendMessage.mockReset()
  })

  it('disables send and shows loading indicator while waiting', async () => {
    sendMessage.mockReturnValue(new Promise(() => {}))
    const { user } = setup()
    await user.type(input(), 'What is the late policy?')
    await user.click(sendButton())
    expect(sendButton()).toBeDisabled()
    expect(screen.getByRole('status', { name: /thinking/i })).toBeInTheDocument()
    expect(screen.getByText('What is the late policy?')).toBeInTheDocument()
  })

  it('greets with a Hello heading when the conversation is empty', () => {
    setup()
    expect(screen.getByRole('heading', { name: /hello/i })).toBeInTheDocument()
    expect(screen.getByText('Ask anything from the knowledge base.')).toBeInTheDocument()
  })

  it('makes the composer glow while thinking', async () => {
    sendMessage.mockReturnValue(new Promise(() => {}))
    const { user } = setup()
    const composer = screen.getByRole('textbox', { name: /message/i }).closest('form')!
    expect(composer).toHaveAttribute('data-state', 'idle')
    await user.type(input(), 'late policy?{Enter}')
    expect(composer).toHaveAttribute('data-state', 'thinking')
  })

  it('does not send empty or whitespace input', async () => {
    const { user } = setup()
    expect(sendButton()).toBeDisabled()
    await user.type(input(), '   ')
    expect(sendButton()).toBeDisabled()
    await user.keyboard('{Enter}')
    expect(sendMessage).not.toHaveBeenCalled()
  })

  it('sends on Enter and reports a newly created session', async () => {
    sendMessage.mockResolvedValue(grounded)
    const { user, onSessionCreated } = setup()
    await user.type(input(), 'late policy?{Enter}')
    expect(sendMessage).toHaveBeenCalledWith('late policy?', undefined)
    expect(await screen.findByText(/per day/)).toBeInTheDocument()
    expect(onSessionCreated).toHaveBeenCalledWith('s1')
    expect(input()).toHaveValue('')
  })

  it('passes the existing session id', async () => {
    sendMessage.mockResolvedValue(grounded)
    const { user, onSessionCreated } = setup({ sessionId: 's1' })
    await user.type(input(), 'more?{Enter}')
    expect(sendMessage).toHaveBeenCalledWith('more?', 's1')
    await screen.findByText(/per day/)
    expect(onSessionCreated).not.toHaveBeenCalled()
  })

  it('shows error banner with Retry on 503; Retry resends the same text', async () => {
    sendMessage
      .mockRejectedValueOnce(new ApiError(503, 'The AI service is busy, please try again.'))
      .mockResolvedValueOnce(grounded)
    const { user } = setup()
    await user.type(input(), 'late policy?{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('The AI service is busy')
    expect(input()).toHaveValue('late policy?')
    await user.click(screen.getByRole('button', { name: /retry/i }))
    expect(sendMessage).toHaveBeenLastCalledWith('late policy?', undefined)
    expect(await screen.findByText(/per day/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getAllByText('late policy?')).toHaveLength(1)
  })

  it('renders sources under a grounded answer', async () => {
    sendMessage.mockResolvedValue(grounded)
    const { user } = setup()
    await user.type(input(), 'late policy?{Enter}')
    const sources = await screen.findByRole('list', { name: /sources/i })
    expect(within(sources).getByText(/Course Handbook/)).toHaveTextContent('Course Handbook, p. 3')
  })

  it('counts characters and blocks messages over 2000', async () => {
    const { user } = setup()
    await user.click(input())
    await user.paste('a'.repeat(2001))
    expect(screen.getByText('2001/2000')).toBeInTheDocument()
    expect(sendButton()).toBeDisabled()
  })

  it('shows earlier messages of the session', () => {
    setup({
      initialMessages: [
        { role: 'user', content: 'hello', sources: [], kind: null },
        { role: 'assistant', content: 'Hi! Ask me anything.', sources: [], kind: 'greeting' },
      ],
    })
    expect(screen.getByText('Hi! Ask me anything.')).toBeInTheDocument()
  })
})
