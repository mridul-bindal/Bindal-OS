import { useEffect, useRef, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

function titleFromFileName(fileName) {
  return fileName
    .replace(/\.txt$/i, '')
    .replace(/^\d+_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function App() {
  const [input, setInput] = useState('')
  const [activeQuery, setActiveQuery] = useState('')
  const [results, setResults] = useState([])
  const [resultMeta, setResultMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [searched, setSearched] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!searched) {
      inputRef.current?.focus()
    }
  }, [searched])

  async function runSearch(rawQuery) {
    const query = rawQuery.trim()
    if (!query) return

    setLoading(true)
    setError('')
    setActiveQuery(query)
    setSearched(true)

    try {
      const response = await fetch(
        `${API_BASE}/api/search?q=${encodeURIComponent(query)}`,
      )
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail || 'Search failed. Please try again.')
      }
      const data = await response.json()
      setResults(data.results ?? [])
      setResultMeta({
        count: data.count ?? 0,
        cleanedQuery: data.cleaned_query ?? query,
      })
    } catch (err) {
      setResults([])
      setResultMeta(null)
      setError(
        err instanceof Error
          ? err.message
          : 'Could not reach the search server.',
      )
    } finally {
      setLoading(false)
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    runSearch(input)
  }

  function goHome() {
    setSearched(false)
    setActiveQuery('')
    setResults([])
    setResultMeta(null)
    setError('')
    setInput('')
  }

  return (
    <div className={`app ${searched ? 'app--results' : 'app--home'}`}>
      <div className="atmosphere" aria-hidden="true" />

      {!searched ? (
        <main className="home">
          <header className="brand">
            <p className="brand__mark">Bindal</p>
            <h1 className="brand__name">SEARCH ENGINE </h1>
            <p className="brand__tagline">Find what matters in your documents.</p>
          </header>

          <form className="search" onSubmit={handleSubmit} role="search">
            <label className="visually-hidden" htmlFor="home-search">
              Search
            </label>
            <div className="search__shell">
              <svg
                className="search__icon"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  d="M10.5 3a7.5 7.5 0 1 1 0 15 7.5 7.5 0 0 1 0-15Zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11Zm8.03 11.47 3 3a1 1 0 0 1-1.41 1.41l-3-3a1 1 0 1 1 1.41-1.41Z"
                  fill="currentColor"
                />
              </svg>
              <input
                id="home-search"
                ref={inputRef}
                className="search__input"
                type="search"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Search documents"
                autoComplete="off"
                spellCheck="false"
              />
              <button className="search__button" type="submit" disabled={loading}>
                Search
              </button>
            </div>
          </form>
        </main>
      ) : (
        <main className="results-page">
          <header className="results-bar">
            <button className="results-bar__logo" type="button" onClick={goHome}>
              <span className="results-bar__logo-mark">Bindal</span>
              <span className="results-bar__logo-name">search</span>
            </button>

            <form className="search search--compact" onSubmit={handleSubmit} role="search">
              <label className="visually-hidden" htmlFor="results-search">
                Search
              </label>
              <div className="search__shell">
                <svg
                  className="search__icon"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    d="M10.5 3a7.5 7.5 0 1 1 0 15 7.5 7.5 0 0 1 0-15Zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11Zm8.03 11.47 3 3a1 1 0 0 1-1.41 1.41l-3-3a1 1 0 1 1 1.41-1.41Z"
                    fill="currentColor"
                  />
                </svg>
                <input
                  id="results-search"
                  className="search__input"
                  type="search"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Search documents"
                  autoComplete="off"
                  spellCheck="false"
                />
                <button className="search__button" type="submit" disabled={loading}>
                  Search
                </button>
              </div>
            </form>
          </header>

          <section className="results" aria-live="polite">
            {loading && <p className="results__status">Searching…</p>}

            {!loading && error && (
              <p className="results__error" role="alert">
                {error}
              </p>
            )}

            {!loading && !error && resultMeta && (
              <p className="results__meta">
                About {resultMeta.count} result
                {resultMeta.count === 1 ? '' : 's'} for “{activeQuery}”
              </p>
            )}

            {!loading && !error && results.length === 0 && resultMeta && (
              <div className="results__empty">
                <h2>No documents matched</h2>
                <p>Try different keywords related to your MongoDB notes.</p>
              </div>
            )}

            {!loading &&
              !error &&
              results.map((hit) => (
                <article key={hit.file_name} className="hit">
                  <p className="hit__path">{hit.file_name}</p>
                  <h2 className="hit__title">{titleFromFileName(hit.file_name)}</h2>
                  {hit.snippet?.length > 0 ? (
                    <p className="hit__snippet">
                      {hit.snippet.join(' … ')}
                    </p>
                  ) : (
                    <p className="hit__snippet hit__snippet--muted">
                      Matching document found.
                    </p>
                  )}
                  <p className="hit__score">Relevance {hit.score.toFixed(2)}</p>
                </article>
              ))}
          </section>
        </main>
      )}

      <footer className="footer">
        <span>Bindal search Engine</span>
        <span>BM25 ranking</span>
      </footer>
    </div>
  )
}

export default App
