import { useEffect, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

export default function DocumentViewer({ fileName, title, onClose }) {
  const dialogRef = useRef(null)
  const [text, setText] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const dialog = dialogRef.current
    dialog.showModal()
    const controller = new AbortController()
    async function load() {
      try {
        const response = await fetch(
          `${API_BASE}/api/document?file_name=${encodeURIComponent(fileName)}`,
          { signal: controller.signal },
        )
        if (!response.ok) {
          throw new Error(response.status === 404
            ? 'This document is no longer available.'
            : 'Could not load this document. Please close and try again.')
        }
        const document = await response.json()
        if (!controller.signal.aborted) setText(document.text)
      } catch (err) {
        if (!controller.signal.aborted) setError(err.message || 'Could not load this document.')
      }
    }
    load()
    return () => {
      controller.abort()
      dialog.close()
    }
  }, [fileName])

  return (
    <dialog ref={dialogRef} className="document-viewer" aria-labelledby="document-title"
      onCancel={(event) => { event.preventDefault(); onClose() }}>
      <header className="document-viewer__header">
        <div>
          <h2 id="document-title">{title}</h2>
          <p className="hit__path">{fileName}</p>
        </div>
        <button type="button" className="search__button" onClick={onClose} autoFocus>
          Close
        </button>
      </header>
      <div className="document-viewer__body">
        {error ? <p className="results__error" role="alert">{error}</p>
          : text === null ? <p role="status">Loading document…</p>
            : <div className="document-viewer__text">{text || 'This document is empty.'}</div>}
      </div>
    </dialog>
  )
}
