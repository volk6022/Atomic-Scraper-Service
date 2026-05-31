// Shared helpers, tiny icons, primitives for the review app.

// ---------- Helpers ----------

function domainOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

function scoreBand(s) {
  if (s == null) return "muted";
  if (s >= 8.5) return "good";
  if (s >= 6.5) return "warn";
  return "bad";
}

function scoreBarWidth(s) {
  if (s == null) return "0%";
  return `${Math.min(100, Math.max(0, (s / 10) * 100))}%`;
}

function fmtNum(n) {
  if (n == null) return "—";
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

function fmtElapsed(s) {
  if (s == null) return "—";
  if (s < 60) return s.toFixed(1) + "s";
  const m = Math.floor(s / 60);
  const r = Math.round(s - m * 60);
  return `${m}:${String(r).padStart(2, "0")}`;
}

function relTime() {
  const opts = ["2m", "14m", "1h", "3h", "yesterday", "2d", "4d"];
  return opts[Math.floor(Math.random() * opts.length)];
}

function isEmpty(v) {
  if (v == null) return true;
  if (typeof v === "string") return v.trim() === "";
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === "object") return Object.keys(v).length === 0;
  return false;
}

function jsonHighlight(obj) {
  let s;
  try { s = JSON.stringify(obj, null, 2); } catch { return String(obj); }
  return s
    .replace(/("(?:[^"\\]|\\.)*")(\s*:)/g, '<span class="json-key">$1</span>$2')
    .replace(/: ("(?:[^"\\]|\\.)*")/g, ': <span class="json-str">$1</span>')
    .replace(/: (-?\d+\.?\d*)/g, ': <span class="json-num">$1</span>')
    .replace(/: (true|false)/g, ': <span class="json-bool">$1</span>')
    .replace(/: (null)/g, ': <span class="json-null">$1</span>')
    .replace(/([{}\[\]])/g, '<span class="json-brace">$1</span>');
}

// ---------- Icons (1em inline SVG) ----------

const Icon = {
  Speak: (p) => (
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" {...p}>
      <path d="M3 6v4h2l3 3V3L5 6H3z"/>
      <path d="M11 5q1.5 1.5 1.5 3T11 11" />
    </svg>
  ),
  Play: (p) => (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" {...p}><path d="M4 3l9 5-9 5z"/></svg>
  ),
  Pause: (p) => (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" {...p}><rect x="4" y="3" width="3" height="10"/><rect x="9" y="3" width="3" height="10"/></svg>
  ),
  Stop: (p) => (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" {...p}><rect x="3" y="3" width="10" height="10"/></svg>
  ),
  Comment: (p) => (
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" {...p}><path d="M2 3h12v8H6l-3 3v-3H2z"/></svg>
  ),
  Edit: (p) => (
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" {...p}><path d="M2 14h4l8-8-4-4-8 8z"/><path d="M10 2l4 4"/></svg>
  ),
  External: (p) => (
    <svg width="9" height="9" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" {...p}><path d="M6 3H3v10h10V10"/><path d="M8 8l5-5"/><path d="M9 3h4v4"/></svg>
  ),
  Search: (p) => (
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" {...p}><circle cx="7" cy="7" r="4"/><path d="M10 10l3 3"/></svg>
  ),
  Rerun: (p) => (
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" {...p}><path d="M3 8a5 5 0 1 0 1.6-3.6"/><path d="M3 2v3h3"/></svg>
  ),
  Check: (p) => (
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M3 8l3 3 7-7"/></svg>
  ),
  Flag: (p) => (
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" {...p}><path d="M3 14V2l7 2-1 4 3 1-2 4z"/></svg>
  ),
  Chevron: (p) => (
    <svg width="9" height="9" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M6 3l5 5-5 5"/></svg>
  ),
  Arrow: (p) => (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" {...p}><path d="M3 8h9m-3-4l4 4-4 4"/></svg>
  ),
};

// ---------- Badge ----------

function Badge({ kind = "default", solid = false, children }) {
  const cls = `badge ${kind !== "default" ? kind : ""} ${solid ? "solid" : ""}`.trim();
  return <span className={cls}>{children}</span>;
}

// ---------- Status dot ----------

function StatusDot({ status }) {
  return <span className={`status-dot ${status}`} title={status} />;
}

// ---------- Score cell ----------

function Score({ value }) {
  if (value == null) return <span className="muted">—</span>;
  const band = scoreBand(value);
  return (
    <span className={`score ${band}`}>
      <span className="score-bar"><i style={{ width: scoreBarWidth(value) }} /></span>
      <span className="tabular">{value.toFixed(1)}</span>
    </span>
  );
}

// ---------- TTS Button (collapse → expand player) ----------

function TTSButton({ text }) {
  const [open, setOpen] = React.useState(false);
  const [playing, setPlaying] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const dur = Math.max(3, Math.min(40, Math.round((text || "").length / 20)));

  React.useEffect(() => {
    if (!open || !playing) return;
    const id = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) { setPlaying(false); return 100; }
        return p + 100 / (dur * 5);
      });
    }, 200);
    return () => clearInterval(id);
  }, [open, playing, dur]);

  function expand() {
    setOpen(true);
    setLoading(true);
    setTimeout(() => { setLoading(false); setPlaying(true); setProgress(0); }, 700);
  }

  function toggle() {
    if (loading) return;
    if (progress >= 100) setProgress(0);
    setPlaying((p) => !p);
  }

  function stop() {
    setPlaying(false);
    setProgress(0);
    setOpen(false);
  }

  if (!open) {
    return (
      <span className="tts" onClick={expand} title="Озвучить блок">
        <Icon.Speak />
        <span>TTS</span>
      </span>
    );
  }

  const cur = Math.round((progress / 100) * dur);
  return (
    <span className="tts expanded">
      {loading
        ? <span className="muted mono" style={{ fontSize: 10 }}>генерация…</span>
        : <span onClick={toggle} style={{ cursor: "pointer" }}>{playing ? <Icon.Pause /> : <Icon.Play />}</span>}
      <span className="tts-time tabular">{`${cur}/${dur}s`}</span>
      <span className="tts-progress"><i style={{ width: `${progress}%` }} /></span>
      <span onClick={stop} style={{ cursor: "pointer", color: "var(--ui-fg-muted)" }}><Icon.Stop /></span>
    </span>
  );
}

// ---------- Editable field with optional comment ----------

function EditableField({ value, multiline = true, editMode, onChange, comment, onComment, placeholder, mono = false }) {
  const [showComment, setShowComment] = React.useState(!!comment);
  const empty = isEmpty(value);

  if (!editMode) {
    return (
      <div className={"field" + (comment ? " has-comment" : "")}>
        {empty
          ? <span className="empty-mark">пусто</span>
          : <span className={mono ? "mono" : ""}>{value}</span>}
        {comment && (
          <div className="field-comment">
            <span className="field-comment-label">Заметка ревьюера</span>
            <div>{comment}</div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={"field" + (comment ? " has-comment" : "")}>
      {multiline
        ? <textarea className="field-input" value={value || ""} placeholder={placeholder || "—"}
                    rows={Math.max(2, Math.min(8, ((value || "").split("\n").length || 1) + 1))}
                    onChange={(e) => onChange(e.target.value)} />
        : <input className="field-input" value={value || ""} placeholder={placeholder || "—"}
                 onChange={(e) => onChange(e.target.value)} />}
      {showComment || comment ? (
        <div className="field-comment">
          <span className="field-comment-label">Комментарий ревьюера</span>
          <textarea value={comment || ""} placeholder="что не так, что уточнить…"
                    onChange={(e) => onComment(e.target.value)} />
        </div>
      ) : (
        <span className="field-add-comment" onClick={() => setShowComment(true)}>
          <Icon.Comment /> + комментарий
        </span>
      )}
    </div>
  );
}

// ---------- Toggle ----------

function Toggle({ checked, onChange, label }) {
  return (
    <span className="toggle" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}>
      <span className="track"><span className="knob" /></span>
      <span>{label}</span>
    </span>
  );
}

// ---------- Toast ----------

function Toast({ msg, onDone }) {
  React.useEffect(() => {
    if (!msg) return;
    const id = setTimeout(onDone, 2200);
    return () => clearTimeout(id);
  }, [msg, onDone]);
  if (!msg) return null;
  return <div className="toast">{msg}</div>;
}

// ---------- Section shell ----------

function Section({ title, children, ttsText, right, anchor }) {
  return (
    <section className="section" id={anchor}>
      <div className="section-head">
        <h2>{title}</h2>
        <div className="tools">
          {ttsText && <TTSButton text={ttsText} />}
          {right}
        </div>
      </div>
      {children}
    </section>
  );
}

Object.assign(window, {
  domainOf, scoreBand, scoreBarWidth, fmtNum, fmtElapsed, relTime, isEmpty, jsonHighlight,
  Icon, Badge, StatusDot, Score, TTSButton, EditableField, Toggle, Toast, Section,
});
