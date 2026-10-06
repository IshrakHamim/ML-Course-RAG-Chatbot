import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as documentsApi from '../api/documents'
import { ApiError } from '../api/client'
import { SourceList } from './SourceList'

vi.mock('../api/documents')
const api = vi.mocked(documentsApi)

describe('SourceList', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    URL.createObjectURL = vi.fn(() => 'blob:pdf-1')
    URL.revokeObjectURL = vi.fn()
  })

  it('opens a PDF source at the cited page', async () => {
    api.getDocumentFile.mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
    const user = userEvent.setup()
    render(
      <SourceList
        sources={[{ document_id: 'd1', title: 'Handbook', source_type: 'pdf', page: 3, url: null }]}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Handbook, p. 3' }))
    const dialog = await screen.findByRole('dialog', { name: 'Handbook, page 3' })
    expect(api.getDocumentFile).toHaveBeenCalledWith('d1')
    expect(await within(dialog).findByTitle('Handbook, page 3')).toHaveAttribute(
      'src',
      'blob:pdf-1#page=3',
    )
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows an error when the file cannot be loaded', async () => {
    api.getDocumentFile.mockRejectedValue(new ApiError(404, 'Document file not found'))
    const user = userEvent.setup()
    render(
      <SourceList
        sources={[{ document_id: 'd1', title: 'Handbook', source_type: 'pdf', page: 1, url: null }]}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Handbook, p. 1' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Document file not found')
  })

  it('keeps text sources and older PDF sources without an id as plain text', () => {
    render(
      <SourceList
        sources={[
          { document_id: 'd2', title: 'Notes', source_type: 'text', page: null, url: null },
          { title: 'Old PDF', source_type: 'pdf', page: 2, url: null },
        ]}
      />,
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('Notes')).toBeInTheDocument()
    expect(screen.getByText('Old PDF, p. 2')).toBeInTheDocument()
  })
})
