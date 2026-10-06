import ReactMarkdown, { type Components } from 'react-markdown'
import type { ChatMessageView } from './chatTypes'
import { SourceList } from './SourceList'
import { Sparkle } from './Sparkle'

const markdownComponents: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
}

export function MessageBubble({ message }: { message: ChatMessageView }) {
  const { role, content, sources, kind } = message
  if (role === 'user') {
    return (
      <div className="bubble user">
        <p className="plain">{content}</p>
      </div>
    )
  }
  return (
    <div className="assistant-row">
      <Sparkle className="avatar" />
      <div className="bubble assistant" data-kind={kind ?? undefined}>
        {kind === 'fallback' && <p className="bubble-label">Not found in the knowledge base</p>}
        <div className="markdown">
          <ReactMarkdown components={markdownComponents}>{content}</ReactMarkdown>
        </div>
        {kind === 'answer' && sources.length > 0 && <SourceList sources={sources} />}
      </div>
    </div>
  )
}
