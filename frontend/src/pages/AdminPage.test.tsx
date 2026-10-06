import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import * as documentsApi from '../api/documents'
import type { DocumentItem } from '../api/types'
import { AdminPage } from './AdminPage'

vi.mock('../api/documents')
const api = vi.mocked(documentsApi)

const handbook: DocumentItem = {
  id: 'd1',
  title: 'Course Handbook',
  source_type: 'pdf',
  source: 'Course Handbook.pdf',
  chunk_count: 12,
  created_at: '2026-10-06T10:00:00Z',
  duplicate: false,
}

function file(name: string, size = 100): File {
  const result = new File(['content'], name)
  Object.defineProperty(result, 'size', { value: size })
  return result
}

async function setup() {
  render(<AdminPage />)
  await screen.findByRole('table')
  return userEvent.setup({ applyAccept: false })
}

describe('AdminPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.listDocuments.mockResolvedValue([handbook])
  })

  it('lists documents with title, type, chunk count', async () => {
    await setup()
    const row = screen.getByRole('row', { name: /Course Handbook/ })
    expect(within(row).getByText('PDF')).toBeInTheDocument()
    expect(within(row).getByText('12')).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    api.listDocuments.mockResolvedValue([])
    render(<AdminPage />)
    expect(await screen.findByText(/no documents yet/i)).toBeInTheDocument()
  })

  it('rejects files over 10 MB or wrong extension before uploading', async () => {
    const user = await setup()
    await user.upload(screen.getByLabelText(/file/i), file('notes.docx'))
    await user.click(screen.getByRole('button', { name: /upload/i }))
    expect(screen.getByRole('alert')).toHaveTextContent('Supported: PDF, TXT, MD')
    await user.upload(screen.getByLabelText(/file/i), file('big.pdf', 10 * 1024 * 1024 + 1))
    await user.click(screen.getByRole('button', { name: /upload/i }))
    expect(screen.getByRole('alert')).toHaveTextContent('larger than 10 MB')
    expect(api.uploadDocument).not.toHaveBeenCalled()
  })

  it('uploads a file and refreshes the list', async () => {
    api.uploadDocument.mockResolvedValue({ ...handbook, id: 'd2', title: 'Notes', chunk_count: 3 })
    const user = await setup()
    await user.upload(screen.getByLabelText(/file/i), file('notes.md'))
    await user.click(screen.getByRole('button', { name: /upload/i }))
    expect(await screen.findByText(/Added "Notes" \(3 chunks\)/)).toBeInTheDocument()
    expect(api.listDocuments).toHaveBeenCalledTimes(2)
  })

  it('shows spinner while uploading and disables inputs', async () => {
    api.uploadDocument.mockReturnValue(new Promise(() => {}))
    const user = await setup()
    await user.upload(screen.getByLabelText(/file/i), file('notes.md'))
    await user.click(screen.getByRole('button', { name: /upload/i }))
    expect(screen.getByRole('status', { name: /adding document/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/file/i)).toBeDisabled()
    expect(screen.getByLabelText(/web page url/i)).toBeDisabled()
  })

  it.each([
    [415, 'Supported: PDF, TXT, MD'],
    [422, 'The PDF has no extractable text (it may be a scanned image)'],
    [503, 'The AI service is busy, please try again.'],
  ])("shows the server's error message on %i", async (status, message) => {
    api.uploadDocument.mockRejectedValue(new ApiError(status, message))
    const user = await setup()
    await user.upload(screen.getByLabelText(/file/i), file('scan.pdf'))
    await user.click(screen.getByRole('button', { name: /upload/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
  })

  it("shows 'Already in knowledge base' when duplicate is true", async () => {
    api.addUrl.mockResolvedValue({ ...handbook, duplicate: true })
    const user = await setup()
    await user.type(screen.getByLabelText(/web page url/i), 'https://example.com/page')
    await user.click(screen.getByRole('button', { name: /add url/i }))
    expect(api.addUrl).toHaveBeenCalledWith('https://example.com/page')
    expect(await screen.findByText(/Already in knowledge base/)).toBeInTheDocument()
  })

  it('asks for confirmation before delete; cancel sends nothing', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = await setup()
    await user.click(screen.getByRole('button', { name: /delete course handbook/i }))
    expect(confirm).toHaveBeenCalled()
    expect(api.deleteDocument).not.toHaveBeenCalled()

    confirm.mockReturnValue(true)
    api.deleteDocument.mockResolvedValue(undefined)
    api.listDocuments.mockResolvedValue([])
    await user.click(screen.getByRole('button', { name: /delete course handbook/i }))
    expect(api.deleteDocument).toHaveBeenCalledWith('d1')
    expect(await screen.findByText(/no documents yet/i)).toBeInTheDocument()
  })
})
