import { useEffect, useState } from 'react'
import { getDocumentFile } from '../api/documents'
import { Spinner } from './Spinner'

export interface PdfTarget {
  documentId: string
  title: string
  page?: number | null
}

interface PdfViewerProps extends PdfTarget {
  onClose: () => void
}

type FileState = { url: string } | { error: string } | null

export function PdfViewer({ documentId, title, page, onClose }: PdfViewerProps) {
  const [file, setFile] = useState<FileState>(null)

  useEffect(() => {
    let url: string | null = null
    let cancelled = false
    getDocumentFile(documentId)
      .then((blob) => {
        if (cancelled) return
        url = URL.createObjectURL(blob)
        setFile({ url })
      })
      .catch((err: unknown) => {
        if (!cancelled) setFile({ error: err instanceof Error ? err.message : String(err) })
      })
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [documentId])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const heading = page != null ? `${title}, page ${page}` : title

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="pdf-viewer"
        role="dialog"
        aria-modal="true"
        aria-label={heading}
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <h2>{heading}</h2>
          {file && 'url' in file && (
            <a href={file.url} target="_blank" rel="noreferrer">
              Open in new tab
            </a>
          )}
          <button type="button" className="icon" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>
        {file === null ? (
          <div className="page-center">
            <Spinner label="Loading PDF" />
          </div>
        ) : 'error' in file ? (
          <p className="error-banner" role="alert">
            {file.error}
          </p>
        ) : (
          <iframe title={heading} src={page != null ? `${file.url}#page=${page}` : file.url} />
        )}
      </div>
    </div>
  )
}
