import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { addUrl, deleteDocument, listDocuments, uploadDocument } from '../api/documents'
import type { DocumentItem } from '../api/types'
import { PdfViewer } from '../components/PdfViewer'
import { Spinner } from '../components/Spinner'

const MAX_UPLOAD_MB = 10
const SUPPORTED_EXTENSIONS = ['.pdf', '.txt', '.md', '.markdown']
const TYPE_LABELS: Record<DocumentItem['source_type'], string> = {
  pdf: 'PDF',
  text: 'Text',
  url: 'Web page',
}

type Notice = { kind: 'success' | 'error'; text: string }

function checkFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!SUPPORTED_EXTENSIONS.some((ext) => name.endsWith(ext))) return 'Supported: PDF, TXT, MD'
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `File is larger than ${MAX_UPLOAD_MB} MB`
  return null
}

function message(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong.'
}

export function AdminPage() {
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [viewing, setViewing] = useState<DocumentItem | null>(null)

  const refresh = useCallback(() => {
    listDocuments()
      .then(setDocuments)
      .catch((err: unknown) => setNotice({ kind: 'error', text: message(err) }))
  }, [])

  useEffect(refresh, [refresh])

  async function add(action: () => Promise<DocumentItem>) {
    setBusy(true)
    setNotice(null)
    try {
      const doc = await action()
      setNotice({
        kind: 'success',
        text: doc.duplicate
          ? `Already in knowledge base: "${doc.title}"`
          : `Added "${doc.title}" (${doc.chunk_count} chunks)`,
      })
      refresh()
      return true
    } catch (err) {
      setNotice({ kind: 'error', text: message(err) })
      return false
    } finally {
      setBusy(false)
    }
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    const problem = checkFile(file)
    if (problem) {
      setNotice({ kind: 'error', text: problem })
      return
    }
    if (await add(() => uploadDocument(file))) {
      setFile(null)
      setFileInputKey((key) => key + 1)
    }
  }

  async function handleUrl(event: FormEvent) {
    event.preventDefault()
    const trimmed = url.trim()
    if (trimmed && (await add(() => addUrl(trimmed)))) setUrl('')
  }

  async function handleDelete(doc: DocumentItem) {
    if (!window.confirm(`Delete "${doc.title}" and all its chunks?`)) return
    try {
      await deleteDocument(doc.id)
      setNotice({ kind: 'success', text: `Deleted "${doc.title}"` })
      refresh()
    } catch (err) {
      setNotice({ kind: 'error', text: message(err) })
    }
  }

  return (
    <main className="admin">
      <h1>Knowledge base</h1>
      <p className="muted">
        Adding a document embeds only that document; deleting one removes its chunks. No retraining
        needed.
      </p>

      <div className="admin-forms">
        <form className="card" onSubmit={handleUpload}>
          <h2>Upload a file</h2>
          <label>
            File (PDF, TXT, MD up to {MAX_UPLOAD_MB} MB)
            <input
              key={fileInputKey}
              type="file"
              accept={SUPPORTED_EXTENSIONS.join(',')}
              disabled={busy}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <button type="submit" className="primary" disabled={busy || !file}>
            Upload
          </button>
        </form>

        <form className="card" onSubmit={handleUrl}>
          <h2>Add a web page</h2>
          <label>
            Web page URL
            <input
              type="url"
              placeholder="https://…"
              value={url}
              disabled={busy}
              onChange={(event) => setUrl(event.target.value)}
            />
          </label>
          <button type="submit" className="primary" disabled={busy || !url.trim()}>
            Add URL
          </button>
        </form>
      </div>

      {busy && (
        <p className="muted">
          <Spinner label="Adding document" /> Adding document… large files can take a while.
        </p>
      )}
      {notice &&
        (notice.kind === 'error' ? (
          <p className="error-banner" role="alert">
            {notice.text}
          </p>
        ) : (
          <p className="success-banner">{notice.text}</p>
        ))}

      <h2>Documents</h2>
      {documents === null ? (
        <Spinner label="Loading documents" />
      ) : documents.length === 0 ? (
        <p className="muted">No documents yet. Upload a file or add a URL to get started.</p>
      ) : (
        <table className="documents">
          <thead>
            <tr>
              <th>Title</th>
              <th>Type</th>
              <th>Chunks</th>
              <th>Added</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.id}>
                <td title={doc.source}>
                  {doc.source_type === 'url' ? (
                    <a href={doc.source} target="_blank" rel="noreferrer">
                      {doc.title}
                    </a>
                  ) : (
                    doc.title
                  )}
                </td>
                <td>{TYPE_LABELS[doc.source_type]}</td>
                <td>{doc.chunk_count}</td>
                <td>{new Date(doc.created_at).toLocaleString()}</td>
                <td>
                  <div className="row-actions">
                    {doc.has_file && (
                      <button
                        type="button"
                        className="secondary"
                        aria-label={`View ${doc.title}`}
                        onClick={() => setViewing(doc)}
                      >
                        View
                      </button>
                    )}
                    <button
                      type="button"
                      className="danger"
                      aria-label={`Delete ${doc.title}`}
                      onClick={() => void handleDelete(doc)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {viewing && (
        <PdfViewer documentId={viewing.id} title={viewing.title} onClose={() => setViewing(null)} />
      )}
    </main>
  )
}
