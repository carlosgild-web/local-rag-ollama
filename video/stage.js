// The stage's own behaviour: no app logic, no data of its own. record.spec.ts calls
// window.stage.* with cues built from the take's capture (decision 0043, ported from
// luna-hybrid-agent).
;(() => {
  const $ = (id) => document.getElementById(id)
  const LAYERS = ['Browser', 'API', 'Ingest', 'Search', 'Prompt', 'Ollama', 'Check', 'SQLite']
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

  function pipeline(active) {
    $('pipeline').innerHTML = LAYERS.map(
      (l, i) => `${i ? '<i>›</i>' : ''}<span class="${l === active ? 'on' : ''}">${esc(l)}</span>`,
    ).join('')
  }

  /** The app frame at `path` (same origin), resolved once it has loaded. */
  function loadApp(path = '/chat') {
    return new Promise((resolve) => {
      const app = $('app')
      app.addEventListener('load', () => resolve(), { once: true })
      app.src = path
    })
  }

  function init({ banner, provider }) {
    $('banner').textContent = banner
    $('provider').textContent = provider
    pipeline(null)
  }

  /** One storyboard row: subtitle, layer, callouts (file:line + excerpt), payload JSON. */
  function show(cue) {
    $('subs').textContent = cue.subtitle || ''
    $('row-id').textContent = cue.id ? `row ${cue.id}` : ''
    if (cue.layer) pipeline(cue.layer)
    $('callouts').innerHTML = (cue.callouts || [])
      .slice(0, cue.payload ? 2 : 3)
      .map((c) => `<div class="callout"><div class="where">${esc(c.file)}:${c.line} · ${esc(c.symbol)}</div><pre>${esc(c.excerpt)}</pre></div>`)
      .join('')
    const box = $('payload')
    if (cue.payload) {
      box.classList.remove('empty')
      $('payload-label').textContent = cue.payload.label
      $('payload-note').textContent = cue.payload.note || ''
      // A text (the prompt) is shown as it is; anything else as JSON.
      const v = cue.payload.value
      $('payload-json').textContent = typeof v === 'string' ? v : JSON.stringify(v, null, 2)
    } else {
      box.classList.add('empty')
    }
    if (cue.slide) slide(cue.slide, cue.slideData)
    else hideSlide()
  }

  const SLIDES = {
    hook: () => `
      <h1>Local RAG with Ollama</h1>
      <p class="lead">Ask questions about your own documents, fully offline. Every answer cites its source, or says it isn't there. Everything runs on this laptop, on Ollama.</p>
      <div class="boxes">
        <div class="box"><b>Add files</b><span>Stored once by their SHA-256, parsed, cut into pieces, embedded with bge-m3.</span></div>
        <div class="box hot"><b>Hybrid search</b><span>Vectors (Chroma) and keywords (SQLite FTS5), fused by rank.</span></div>
        <div class="box"><b>Grounded answers</b><span>The model sees only the passages, and every citation is checked.</span></div>
        <div class="box"><b>Versions</b><span>A changed file is v2; rollback flips a pointer, no re-embedding.</span></div>
      </div>`,
    end: (d) => `
      <h1>Every answer cites its source, or says it isn't there.</h1>
      <p class="lead" style="margin-bottom:34px">Every answer stores the passages and scores it used.</p>
      <p class="lead">${esc(d.repo || '')}</p>
      ${d.author ? `<p class="lead" style="margin-top:34px">${esc(d.author)}</p>` : ''}
      ${d.linkedin ? `<p class="lead">${esc(d.linkedin)}</p>` : ''}`,
  }

  function slide(name, data = {}) {
    $('slide-inner').innerHTML = SLIDES[name](data)
    $('slide').classList.add('on')
  }

  function hideSlide() {
    $('slide').classList.remove('on')
  }

  /** The app frame's text, without what the recorder masks: for the no-paths check. */
  function appText() {
    const doc = $('app').contentDocument
    if (!doc) return ''
    const clone = doc.body.cloneNode(true)
    clone.querySelectorAll('[data-video-masked]').forEach((n) => n.remove())
    return clone.innerText || clone.textContent || ''
  }

  window.stage = { init, loadApp, show, slide, hideSlide, appText }
})()
