import { useEffect, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

export default function AISummary({ query }) {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const request = useRef(null)

  useEffect(() => () => request.current?.abort(), [])

  async function generate() {
    if (loading) return
    const controller = new AbortController()
    request.current = controller
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/api/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'AI summary is unavailable. Please try again.')
      if (!controller.signal.aborted) setSummary(data)
    } catch (err) {
      if (!controller.signal.aborted) setError(err.message || 'Could not generate the summary.')
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  return (
    <section className="ai-summary hit" aria-label="AI summary" aria-busy={loading}>
      <div className="ai-summary__header">
        <h2 className="hit__title">AI summary</h2>
        {!summary && <button className="search__button" type="button" onClick={generate} disabled={loading}>
          {loading ? 'Generating…' : error ? 'Retry summary' : 'Generate summary'}
        </button>}
      </div>
      <div aria-live="polite">
        {loading && <p className="results__status">Preparing an answer from your search sources…</p>}
        {error && <p className="results__error" role="alert">{error}</p>}
        {summary && <>
          <p className="hit__snippet ai-summary__answer">{summary.answer}</p>
          {summary.sources.length > 0 && <ul className="ai-summary__sources">
            {summary.sources.map((source) => <li key={source.source_number}>
              [{source.source_number}]{' '}
              {/^https?:\/\//i.test(source.url || '')
                ? <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>
                : source.title}
              {source.domain && <span className="hit__path"> — {source.domain}</span>}
            </li>)}
          </ul>}
        </>}
      </div>
    </section>
  )
}
