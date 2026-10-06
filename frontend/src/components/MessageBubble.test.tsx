import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MessageBubble } from './MessageBubble'

describe('MessageBubble', () => {
  it("marks kind=fallback bubble with data-kind='fallback' and no sources", () => {
    const { container } = render(
      <MessageBubble
        message={{
          role: 'assistant',
          content: "I couldn't find that in the knowledge base.",
          sources: [{ title: 'Doc', source_type: 'text', page: null, url: null }],
          kind: 'fallback',
        }}
      />,
    )
    expect(container.querySelector('[data-kind="fallback"]')).not.toBeNull()
    expect(screen.getByText(/not found in the knowledge base/i)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: /sources/i })).not.toBeInTheDocument()
  })

  it('greeting bubble is not styled as fallback', () => {
    const { container } = render(
      <MessageBubble
        message={{ role: 'assistant', content: 'Hi!', sources: [], kind: 'greeting' }}
      />,
    )
    expect(container.querySelector('[data-kind="greeting"]')).not.toBeNull()
    expect(container.querySelector('[data-kind="fallback"]')).toBeNull()
    expect(screen.queryByText(/not found in the knowledge base/i)).not.toBeInTheDocument()
  })

  it('renders markdown but not raw HTML', () => {
    const { container } = render(
      <MessageBubble
        message={{
          role: 'assistant',
          content: '**bold** <img src=x onerror=alert(1)>',
          sources: [],
          kind: 'answer',
        }}
      />,
    )
    expect(container.querySelector('strong')).toHaveTextContent('bold')
    expect(container.querySelector('img')).toBeNull()
  })

  it('opens links in a new tab safely', () => {
    render(
      <MessageBubble
        message={{
          role: 'assistant',
          content: '[site](https://example.com)',
          sources: [],
          kind: 'answer',
        }}
      />,
    )
    const link = screen.getByRole('link', { name: 'site' })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer')
  })

  it('links URL sources', () => {
    render(
      <MessageBubble
        message={{
          role: 'assistant',
          content: 'Answer',
          sources: [
            { title: 'Wiki', source_type: 'url', page: null, url: 'https://example.com/wiki' },
          ],
          kind: 'answer',
        }}
      />,
    )
    expect(screen.getByRole('link', { name: 'Wiki' })).toHaveAttribute(
      'href',
      'https://example.com/wiki',
    )
  })
})
