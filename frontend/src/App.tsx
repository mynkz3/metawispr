import { useEffect, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent, ReactNode } from 'react';
import type { Edit, Evidence, Fact, Health, Meeting, Stage, View } from './types';

const active = (stage: Stage) => ['queued', 'preparing', 'transcribing', 'refining', 'documenting'].includes(stage);
const labels: Record<Stage, string> = {
  queued: 'In the queue', preparing: 'Preparing audio', transcribing: 'Transcribing', transcribed: 'Transcript ready',
  refining: 'Refining terminology', documenting: 'Writing the record', complete: 'Ready for review', failed: 'Needs attention',
};
const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const date = (value: string) => new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
const initialSelection = () => {
  const value = new URLSearchParams(location.search).get('meeting');
  return value && /^[a-f0-9-]{36}$/.test(value) ? value : null;
};
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, signal: options.signal ?? AbortSignal.timeout(120000) });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status}). Please try again.`);
  }
  return response.json();
}
function Icon({ name }: { name: 'upload' | 'arrow' | 'source' | 'plus' | 'menu' | 'focus' }) {
  const paths = { menu: 'M4 6h16M4 12h16M4 18h16', focus: 'M8 4H4v4m12-4h4v4M4 16v4h4m12-4v4h-4', upload: 'M12 16V4m-5 5 5-5 5 5M4 16v4h16v-4', arrow: 'M5 12h14m-6-6 6 6-6 6', source: 'M8 10H5v7h6v-7H8V6H5m12 4h-3v7h6v-7h-3V6h-3', plus: 'M12 5v14M5 12h14' };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
function Empty({ children }: { children: ReactNode }) { return <p className="empty-note">{children}</p>; }

export default function App() {
  const [libraryOpen, setLibraryOpen] = useState(() => window.matchMedia('(min-width: 1100px)').matches);
  const [focusMode, setFocusMode] = useState(false);
  const libraryButton = useRef<HTMLButtonElement>(null);
  const header = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = header.current;
    if (!element) return;
    const observer = new ResizeObserver(() => document.documentElement.style.setProperty('--header-height', `${element.offsetHeight}px`));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const [selected, setSelected] = useState(initialSelection);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [libraryError, setLibraryError] = useState('');
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [tab, setTab] = useState('Overview');
  const [rawMode, setRawMode] = useState(false);
  const [source, setSource] = useState<Evidence | null>(null);
  const [sourceOrigin, setSourceOrigin] = useState('refined transcript');
  const audio = useRef<HTMLAudioElement>(null);
  const sourcePanel = useRef<HTMLElement>(null);
  const pendingSeek = useRef<number | null>(null);
  const [audioError, setAudioError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    request<{ meetings: Meeting[] }>('/api/meetings', { signal: controller.signal })
      .then(data => { setMeetings(data.meetings); setLibraryError(''); })
      .catch(err => { if (!controller.signal.aborted) setLibraryError(err.message); });
    request<Health>('/api/health', { signal: controller.signal }).then(setHealth).catch(() => {});
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    const pop = () => setSelected(initialSelection());
    window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, []);

  useEffect(() => {
    setView(null); setError(''); setSource(null); setTab('Overview'); setRawMode(false); setAudioError(''); pendingSeek.current = null;
    if (!selected) { setLoading(false); return; }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    async function poll() {
      try {
        const result = await request<View>(`/api/meetings/${selected}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setView(result); setError(''); setLoading(false);
        setMeetings(previous => [result.meeting, ...previous.filter(m => m.id !== result.meeting.id)].sort((a, b) => b.created_at.localeCompare(a.created_at)));
        if (active(result.meeting.stage)) timer = setTimeout(poll, 2000);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Could not load this recording.'); setLoading(false);
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [selected, refresh]);

  const meeting = view?.meeting;
  useEffect(() => {
    if (!meeting || !active(meeting.stage)) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [meeting?.stage]);

  function choose(id: string | null) {
    const url = new URL(location.href);
    if (id) url.searchParams.set('meeting', id); else url.searchParams.delete('meeting');
    history.pushState(null, '', url); setSelected(id);
    if (!window.matchMedia('(min-width: 1100px)').matches) setLibraryOpen(false);
    requestAnimationFrame(() => document.getElementById('workspace')?.focus({ preventScroll: true }));
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  async function resume(kind: 'retry' | 'document') {
    if (!meeting) return;
    setBusy(true); setError('');
    try { await request(`/api/meetings/${meeting.id}/${kind}`, { method: 'POST' }); setRefresh(n => n + 1); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not resume processing.'); }
    finally { setBusy(false); }
  }
  const sourceSegment = source ? (view?.refined?.segments ?? view?.raw?.segments)?.find(s => s.id === source.segment_id) : null;
  function seek() {
    if (audio.current && pendingSeek.current !== null && audio.current.readyState > 0 && audio.current.seekable.length > 0) {
      audio.current.currentTime = pendingSeek.current; pendingSeek.current = null;
    }
  }
  function showSource(evidence: Evidence, origin = view?.refined ? 'refined transcript' : 'raw transcript') {
    const segment = (view?.refined?.segments ?? view?.raw?.segments)?.find(s => s.id === evidence.segment_id);
    if (!segment) return;
    setSource(evidence); setSourceOrigin(origin); setAudioError(''); pendingSeek.current = segment.start; seek();
    requestAnimationFrame(() => { sourcePanel.current?.focus({ preventScroll: true }); sourcePanel.current?.scrollIntoView({ block: 'nearest', behavior: 'instant' }); });
  }
  function sources(items: Evidence[]) {
    return <div className="sources">{items.map((e, i) => <button className="source-button" key={`${e.segment_id}-${i}`} onClick={() => showSource(e)} aria-label={`Open source ${i + 1}: ${e.quote}`}><Icon name="source" /> Source {items.length > 1 ? i + 1 : ''}</button>)}</div>;
  }
  function facts(items: Fact[], empty: string) {
    return items.length ? <ul className="fact-list">{items.map((fact, i) => <li key={i}><p>{fact.text}</p>{sources(fact.evidence)}</li>)}</ul> : <Empty>{empty}</Empty>;
  }
  const record = view?.document?.record;
  const ready = !!health?.transcription_ready && !!health?.llm_ready;
  const exports = view ? [
    ...(view.document ? [['meeting.md', 'Meeting notes · Markdown'], ['meeting.json', 'Meeting record · JSON'], ['bundle.zip', 'All artifacts · ZIP'], ['provenance.json', 'Model provenance · JSON']] : []),
    ...(view.refined ? [['refined.txt', 'Refined transcript · Text'], ['refined.json', 'Refined transcript · JSON'], ['edits.json', 'Correction history · JSON']] : []),
    ...(view.raw ? [['raw.txt', 'Raw transcript · Text'], ['raw.json', 'Raw transcript · JSON']] : []),
  ] : [];
  const tabs = ['Overview', 'Decisions', 'Tasks', 'Transcript'];
  function tabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
    if (next !== null) { event.preventDefault(); setTab(tabs[next]); document.getElementById(`tab-${tabs[next]}`)?.focus(); }
  }

  return <div className={`app-shell ${libraryOpen && !focusMode ? 'library-open' : ''} ${focusMode ? 'focus-mode' : ''}`} onClick={event => {
    if (!(event.target as Element).closest('.exports')) document.querySelector<HTMLDetailsElement>('.exports')?.removeAttribute('open');
  }} onKeyDown={event => {
    const menu = document.querySelector<HTMLDetailsElement>('.exports');
    if (event.key === 'Escape' && menu?.open) { menu.open = false; menu.querySelector('summary')?.focus(); }
    else if (event.key === 'Escape' && libraryOpen) { setLibraryOpen(false); libraryButton.current?.focus(); }
  }}>
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <header ref={header} className="app-header">
      <button ref={libraryButton} className="secondary library-toggle" aria-label="Meeting library" aria-controls="meeting-library" aria-expanded={libraryOpen && !focusMode} onClick={() => { setFocusMode(false); setLibraryOpen(!libraryOpen || focusMode); }}><Icon name="menu" /><span>Library</span></button>
      <a className="brand" href="/" onClick={e => { e.preventDefault(); choose(null); }}><img src="/mark.svg" alt="" width="34" height="34" />Metawispr</a>
      <div className="header-context"><span>{meeting?.title ?? 'Meeting notebook'}</span><span className="header-status">{meeting ? view?.document?.unavailable_sections?.length ? 'Partial record' : labels[meeting.stage] : 'Local processing'}</span></div>
      <div className="header-actions"><button className="secondary focus-button" aria-pressed={focusMode} onClick={() => setFocusMode(!focusMode)}><Icon name="focus" /><span>{focusMode ? 'Exit focus mode' : 'Focus mode'}</span></button><button className="new-button" onClick={() => choose(null)}><Icon name="plus" /><span>New recording</span></button>
      {exports.length > 0 && <details className="exports"><summary className="secondary">Download <span aria-hidden="true">↓</span></summary><div className="export-menu">{exports.map(([format, label]) => <a key={format} href={`/api/meetings/${meeting!.id}/export/${format}`} download onClick={e => e.currentTarget.closest('details')?.removeAttribute('open')}>{label}</a>)}</div></details>}</div>
    </header>
    {libraryOpen && !focusMode && <button className="library-backdrop" aria-label="Close meeting library" onClick={() => { setLibraryOpen(false); libraryButton.current?.focus(); }} />}
    <aside id="meeting-library" className="rail" aria-label="Meeting library" hidden={!libraryOpen || focusMode}>
      <details className="library" open><summary>YOUR RECORDINGS <span>{meetings.length}</span></summary>
        {libraryError ? <div className="library-error"><p>{libraryError}</p><button className="text-button" onClick={() => setRefresh(n => n + 1)}>Reload library</button></div> : meetings.length ? <nav aria-label="Recent recordings">{meetings.map(m => <a key={m.id} href={`?meeting=${m.id}`} className={`meeting-link ${selected === m.id ? 'selected' : ''}`} aria-current={selected === m.id ? 'page' : undefined} onClick={e => { e.preventDefault(); choose(m.id); }}><span className="meeting-title">{m.title}</span><span className="meeting-meta"><i className={`dot ${m.stage}`} />{labels[m.stage]}</span></a>)}</nav> : <p className="library-empty">Your recordings will live here.<br />Start with a conversation.</p>}
      </details>
      <div className="rail-footer"><span className="local-indicator" />Local workspace<p>Audio and notes stay on this machine.</p></div>
    </aside>
    <main id="workspace" tabIndex={-1}>

      {!selected ? <Upload health={health} onUploaded={m => { setMeetings(prev => [m, ...prev]); choose(m.id); }} /> : <>
        {loading && !view && <p role="status" className="loading">Opening your recording…</p>}
        {error && <div className="error-box" role="alert"><strong>We couldn’t finish this request.</strong><p>{error}</p><button className="secondary" onClick={() => setRefresh(n => n + 1)}>Reload recording</button>{!view && <p>If speech recognition finished, <a href={`/api/meetings/${selected}/export/raw.txt`} download>download the saved raw transcript</a>.</p>}</div>}
        {meeting && <>
          <header className="record-header"><div><p className="eyebrow">{date(meeting.created_at)} {meeting.duration_seconds ? `· ${clock(meeting.duration_seconds)} recording` : ''}</p><h1>{meeting.title}</h1><p className="filename">{meeting.filename}</p></div></header>
          <section className={`status-card ${meeting.stage}`} aria-label="Processing status">
            <div className="status-title"><span className={`status-mark ${active(meeting.stage) ? 'working' : ''}`} aria-hidden="true">{meeting.stage === 'complete' ? '✓' : meeting.stage === 'failed' ? '!' : '◌'}</span><div><h2 aria-live="polite">{labels[meeting.stage]}</h2><p>{meeting.stage === 'complete' ? 'Review the interpretation alongside its sources.' : meeting.stage === 'failed' ? `Stopped while ${labels[meeting.failed_stage ?? 'queued'].toLowerCase()}. Completed stages are saved.` : meeting.stage === 'transcribed' ? 'The raw transcript is saved. Continue to create the meeting record.' : 'One local worker is processing your recording. You can return to it from the library.'}</p></div>{active(meeting.stage) && <span className="elapsed">{clock(Math.max(0, (now - Date.parse(meeting.created_at)) / 1000))} elapsed</span>}</div>
            <ol className="steps">{(['preparing', 'transcribing', 'refining', 'documenting'] as Stage[]).map((s, i) => {
              const current = meeting.stage === 'failed' ? meeting.failed_stage : meeting.stage;
              const index = current === 'complete' ? 4 : current === 'transcribed' ? 2 : ['preparing', 'transcribing', 'refining', 'documenting'].indexOf(current ?? 'queued');
              return <li key={s} className={i < index ? 'done' : s === current ? 'current' : ''}><span aria-hidden="true">{i < index ? '✓' : `0${i + 1}`}</span>{['Prepare audio', 'Transcribe', 'Refine terminology', 'Write record'][i]}</li>;
            })}</ol>
            {meeting.stage === 'transcribing' && <p className="progress-detail">{clock(meeting.processed_audio_seconds)} of {clock(meeting.duration_seconds ?? 0)} audio processed</p>}
            {meeting.stage === 'failed' && <div className="failure"><p role="alert">{meeting.error}</p>{meeting.retryable ? <button className="primary" disabled={busy} onClick={() => void resume('retry')}>{busy ? 'Resuming…' : 'Retry from saved progress'}<Icon name="arrow" /></button> : <button className="secondary" onClick={() => choose(null)}>Upload another recording</button>}</div>}
            {meeting.stage === 'transcribed' && <button className="primary" disabled={busy} onClick={() => void resume('document')}>{busy ? 'Starting…' : 'Create meeting record'}<Icon name="arrow" /></button>}
          </section>
          <div className="review-grid"><section className="review-content" aria-label="Meeting review">
            {!!view.document?.unavailable_sections?.length && <p role="status" className="small-note">Partial record: {view.document.unavailable_sections.join(' and ')} are unavailable because generation or validation failed. The validated summary remains available.</p>}
            <div className="tabs" role="tablist" aria-label="Record views">{tabs.map((name, index) => <button key={name} role="tab" id={`tab-${name}`} aria-controls="record-panel" aria-selected={tab === name} tabIndex={tab === name ? 0 : -1} onKeyDown={e => tabKey(e, index)} onClick={() => setTab(name)}>{name}{name === 'Decisions' && record && !view.document?.unavailable_sections?.includes('decisions') && <span>{record.decisions.length}</span>}{name === 'Tasks' && record && !view.document?.unavailable_sections?.includes('tasks') && <span>{record.tasks.length}</span>}</button>)}</div>
            <div id="record-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} tabIndex={0} className="record-panel">
              {tab === 'Transcript' ? <>
                <div className="section-heading"><div><p className="eyebrow">THE CONVERSATION</p><h2>Transcript</h2></div><div className="toggle" role="group" aria-label="Transcript version"><button aria-pressed={!rawMode} disabled={!view.refined} onClick={() => setRawMode(false)}>Refined</button><button aria-pressed={rawMode || !view.refined} onClick={() => setRawMode(true)}>Raw</button></div></div>
                <p className="small-note">Raw speech recognition is preserved. Times mark audio windows, not individual words.</p>
                {(rawMode || !view.refined ? view.raw?.segments : view.refined.segments)?.map(s => <article className="transcript-segment" key={s.id}><button className="time-button" aria-label={`Open audio window ${clock(s.start)} to ${clock(s.end)}`} onClick={() => showSource({ segment_id: s.id, quote: s.text }, rawMode || !view.refined ? 'raw transcript' : 'refined transcript')}>{clock(s.start)} — {clock(s.end)}</button><p>{s.text}</p></article>)}
                {!view.raw && <Empty>The transcript will appear after speech recognition finishes.</Empty>}
                {view.refined && <details className="audit"><summary>Correction history <span>{view.refined.accepted.length} accepted · {view.refined.rejected.length} rejected</span></summary>
                  {view.refined.accepted.length === 0 && <Empty>No terminology changes were accepted.</Empty>}
                  {view.refined.accepted.map((edit, i) => <EditRow key={i} edit={edit} label="Accepted" onSource={() => showSource({ segment_id: edit.segment_id, quote: edit.replacement })} />)}
                  {view.refined.rejected.map(({ edit, rejection }, i) => <EditRow key={i} edit={edit} label={`Rejected · ${rejection}`} onSource={view.raw?.segments.some(s => s.id === edit.segment_id) ? () => showSource({ segment_id: edit.segment_id, quote: edit.original }, 'raw transcript · rejected proposal') : undefined} />)}
                  {view.refined.warnings.map((warning, i) => <p key={i} className="small-note">{warning}</p>)}
                </details>}
              </> : !record ? <Empty>{meeting.stage === 'failed' ? 'The meeting record is not available. You can still inspect and download completed transcripts.' : 'Notes, decisions and tasks will appear after documentation finishes.'}</Empty> : tab === 'Decisions' ? <><p className="eyebrow">AGREED IN THE MEETING</p><h2>Decisions</h2>{facts(record.decisions, view.document?.unavailable_sections?.includes('decisions') ? 'Unavailable: decision generation or validation failed.' : 'No agreed decisions were extracted. Check the minutes and sources for omissions.')}</> : tab === 'Tasks' ? <><p className="eyebrow">WHAT HAPPENS NEXT</p><h2>Tasks</h2>{record.tasks.length ? <div className="task-list">{record.tasks.map((task, i) => <article className="task" key={i}><span className="item-number" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span><div><h3>{task.text}</h3><dl><div><dt>Owner</dt><dd className={!task.owner ? 'unspecified' : ''}>{task.owner ?? 'Unspecified'}</dd></div><div><dt>Deadline</dt><dd className={!task.deadline ? 'unspecified' : ''}>{task.deadline ?? 'Unspecified'}</dd></div></dl>{sources(task.evidence)}</div></article>)}</div> : <Empty>{view.document?.unavailable_sections?.includes('tasks') ? 'Unavailable: task generation or validation failed.' : 'No tasks were extracted. Check the minutes and sources for omissions.'}</Empty>}<p className="small-note">Assignments and dates appear only when stated in the conversation. Relative dates remain as spoken.</p></> : <>
                <p className="eyebrow">AT A GLANCE</p><h2>Meeting summary</h2>{facts(record.summary, 'No summary points were extracted.')}
                <div className="section-heading minutes-heading"><h2>Meeting minutes</h2><span className="small-note">{record.topics.length} topics</span></div>{record.topics.map((topic, i) => <section className="topic" key={i}><h3>{topic.title}</h3>{facts(topic.points, 'No points.')}</section>)}
                {record.uncertainties.length > 0 && <section className="review-notes"><h3>To clarify</h3><ul>{record.uncertainties.map((note, i) => <li key={i}>{note}</li>)}</ul></section>}
                {(view.document?.revision_audit.length ?? 0) > 0 && <details className="audit"><summary>Revision history <span>{view.document!.revision_audit.length} entries</span></summary><p className="small-note">Earlier commitments and later changes are retained here for review.</p>{facts(view.document!.revision_audit, 'No revisions.')}</details>}
              </>}
            </div>
          </section>
          <aside className="source-panel" ref={sourcePanel} tabIndex={-1} aria-label="Source audio and evidence"><p className="eyebrow">BACK TO THE SOURCE</p><h2>Source notebook</h2><p className="small-note">Select a source to check what was said.</p>{view.raw ? <audio key={meeting.id} ref={audio} controls preload="metadata" src={`/api/meetings/${meeting.id}/audio`} onLoadedMetadata={seek} onCanPlay={seek} onProgress={seek} onError={() => setAudioError('Audio could not load. Reload this recording to try again.')} aria-label="Meeting recording" /> : <Empty>Audio playback appears with the transcript.</Empty>}
            {audioError && <p role="alert" className="audio-error">{audioError}</p>}
            {source && sourceSegment ? <div className="quote-card"><span className="quote-label">{source.segment_id} · {clock(sourceSegment.start)} — {clock(sourceSegment.end)}</span><blockquote>{source.quote}</blockquote><p className="small-note">Audio window · {sourceOrigin}. Timestamps identify windows, not exact word alignment.</p></div> : <div className="source-placeholder"><Icon name="source" /><p>Every extracted point has a source. Open one to see the exact quote.</p></div>}
            <div className="review-reminder"><strong>A record to review.</strong><p>Matching quotes help you trace a claim. They still need your judgment about its meaning.</p></div>
          </aside></div>
        </>}
      </>}
      <footer className="workspace-footer"><span>Less recall. More clarity.</span><span>{health ? ready ? 'Local models ready' : 'Setup needs attention' : libraryError ? 'Local service unavailable' : 'Connecting to local service'}</span></footer>
    </main>
  </div>;
}

function EditRow({ edit, label, onSource }: { edit: Edit; label: string; onSource?: () => void }) {
  return <article className="edit-row"><p className="eyebrow">{label}</p><p><del>{edit.original}</del> <span aria-hidden="true">→</span> <ins>{edit.replacement}</ins></p><p className="small-note">{edit.reason}</p>{onSource && <button className="source-button" onClick={onSource}><Icon name="source" /> Inspect window</button>}</article>;
}

function Upload({ health, onUploaded }: { health: Health | null; onUploaded: (meeting: Meeting) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [glossary, setGlossary] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const formats = ['wav', 'mp3', 'm4a', 'flac', 'ogg', 'webm'];
  function pick(candidate?: File) {
    setError('');
    if (!candidate) return;
    setFile(null);
    if (!formats.includes(candidate.name.split('.').pop()?.toLowerCase() ?? '')) { setError('Choose a WAV, MP3, M4A, FLAC, OGG or WEBM recording.'); return; }
    if (candidate.size === 0) { setError('This recording is empty. Choose another file.'); return; }
    if (health && candidate.size > health.limits.upload_bytes) { setError(`The recording exceeds the ${Math.floor(health.limits.upload_bytes / 1048576)} MB limit.`); return; }
    setFile(candidate);
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) { setError('Choose a recording first.'); input.current?.focus(); return; }
    setBusy(true); setError('');
    const body = new FormData(); body.append('file', file); body.append('title', title); body.append('glossary', glossary);
    try { onUploaded(await request<Meeting>('/api/meetings', { method: 'POST', body })); }
    catch (err) { setError(err instanceof Error ? err.message : 'Upload failed. Please try again.'); }
    finally { setBusy(false); }
  }
  const incomplete = health && (!health.transcription_ready || !health.llm_ready || !health.conversion_ready);
  return <div className="upload-workspace"><header className="hero"><p className="eyebrow">YOUR MEETING NOTEBOOK</p><h1>A place for the conversation.</h1><p>Upload an English recording to create notes with sources you can review.</p></header>
    <div className="upload-grid"><form className="upload-card" onSubmit={e => void submit(e)} aria-label="Upload a meeting recording"><div className="card-heading"><h2>Start with a recording</h2><span>01</span></div>
      <div className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); if (!busy) { if (e.dataTransfer.files.length !== 1) setError('Choose one recording at a time.'); else pick(e.dataTransfer.files[0]); } }}>
        <span className="upload-icon"><Icon name="upload" /></span><strong>{file ? file.name : 'A conversation starts here.'}</strong><p>{file ? `${(file.size / 1048576).toFixed(1)} MB · ready to upload` : 'Drop your audio file, or choose one below.'}</p><label className={`secondary file-button ${busy ? 'disabled' : ''}`}><input ref={input} type="file" accept=".wav,.mp3,.m4a,.flac,.ogg,.webm" aria-label="Choose recording" disabled={busy} onChange={e => { pick(e.target.files?.[0]); e.target.value = ''; }} />{file ? 'Change recording' : 'Choose recording'}</label>
        <p className="format-hint">WAV · MP3 · M4A · FLAC · OGG · WEBM{health && <><br />Up to {Math.floor(health.limits.upload_bytes / 1048576)} MB · {Math.floor(health.limits.audio_seconds / 60)} minutes</>}</p>
      </div>
      <label className="field">Meeting title <span>Optional</span><input type="text" maxLength={200} placeholder="e.g. Product planning" value={title} disabled={busy} onChange={e => setTitle(e.target.value)} /></label>
      <details className="glossary"><summary>Add terminology <span>Optional</span></summary><label className="field" htmlFor="glossary">Words worth getting right</label><textarea id="glossary" rows={4} maxLength={10000} value={glossary} disabled={busy} onChange={e => setGlossary(e.target.value)} placeholder={'Docker\nPostgreSQL\ndock her => Docker'} /><p className="small-note">One canonical term per line. You can add an alias as “alias =&gt; canonical.” Raw speech recognition stays available.</p></details>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary submit" disabled={busy} type="submit">{busy ? 'Uploading recording…' : 'Create the meeting record'}<Icon name="arrow" /></button>
      <p className="privacy-note">English recordings · processed locally on this machine</p>
      {incomplete && <details className="setup"><summary>Local setup needs attention</summary><p>Install the required models before processing. The recording can be retried if setup is incomplete.</p>{health.llm_error && <p>{health.llm_error}</p>}<pre>uv sync --locked{'\n'}uv run python -m metawispr download-model{'\n'}ollama pull qwen3.5:4b{'\n'}ollama serve</pre><p>Run from the repository root. Use <code>uv run python -m metawispr doctor</code> to check readiness.</p></details>}
    </form>
    <details className="how-it-works"><summary>How your record is created</summary><p>Audio is prepared, transcribed, refined with your glossary and turned into a validated meeting record. Review the summary, minutes, decisions and tasks alongside their source audio.</p><p>Raw speech recognition and correction history remain available. A valid summary stays accessible when another section is unavailable.</p></details></div>
  </div>;
}
