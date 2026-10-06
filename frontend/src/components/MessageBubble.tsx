import ReactMarkdown, { type Components } from 'react-markdown'
import type { ChatMessageView } from './chatTypes'
import { SourceList } from './SourceList'

const markdownComponents: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
}

export function MessageBubble({ message }: { message: ChatMessageView }) {
  const { role, content, sources, kind } = message
  return (
    <div className={`bubble ${role}`} data-kind={kind ?? undefined}>
      {kind === 'fallback' && <p className="bubble-label">Not found in the knowledge base</p>}
      {role === 'assistant' ? (
        <div className="markdown">
          <ReactMarkdown components={markdownComponents}>{content}</ReactMarkdown>
        </div>
      ) : (
        <p className="plain">{content}</p>
      )}
      {kind === 'answer' && sources.length > 0 && <SourceList sources={sources} />}
    </div>
  )
}
