// Trace timeline — vertical with central branch.

function TraceTimeline({ trace, criticEvents }) {
  // Merge critic events into trace (already there in real data, but ensure)
  const items = trace || [];
  if (!items.length) {
    return <div style={{ padding: 24, color: "var(--ui-fg-faint)", fontSize: 12 }}>Trace недоступен.</div>;
  }

  // Group by turn so we can label the central branch
  const turns = [];
  let cur = null;
  items.forEach((it) => {
    if (!cur || cur.turn !== it.turn) {
      cur = { turn: it.turn, items: [] };
      turns.push(cur);
    }
    cur.items.push(it);
  });

  return (
    <div className="timeline">
      {turns.map((t, ti) => (
        <div key={ti} style={{ position: "relative", paddingTop: 20 }}>
          <div className="tl-turn-label">TURN {String(t.turn).padStart(2, "0")}</div>
          {t.items.map((it, i) => {
            const side = it.role === "assistant" ? "left" : "right";
            const dotKind = it.role;
            const label = {
              assistant: "model",
              tool: it.tool || "tool",
              critic: "CRITIC",
              refraser: "REFRASER",
              note: "note",
              error: "ERROR",
            }[it.role] || it.role;

            let body = null;
            if (it.role === "critic") {
              body = (
                <>
                  <div className="tl-tool">
                    score <span className="tabular">{it.score?.toFixed(1)}</span> · {it.verdict}
                  </div>
                  <div className="tl-preview">{it.feedback}</div>
                  {it.missing?.length > 0 && <div className="tl-meta">missing: {it.missing.join(", ")}</div>}
                </>
              );
            } else if (it.role === "assistant") {
              body = (
                <>
                  <div className="tl-tool">{it.tool}({it.args?.slice(0, 60)}{it.args?.length > 60 ? "…" : ""})</div>
                  {it.tokens && <div className="tl-meta">prompt {fmtNum(it.tokens)} tok · {fmtElapsed(it.elapsed_s)}</div>}
                </>
              );
            } else {
              const ok = it.ok !== false;
              body = (
                <>
                  <div className="tl-tool" style={{ color: ok ? "var(--ui-fg)" : "var(--signal-bad)" }}>
                    {ok ? it.tool : `${it.tool} · FAIL`}
                  </div>
                  <div className="tl-preview">{it.preview?.slice(0, 200)}{it.preview?.length > 200 ? "…" : ""}</div>
                  <div className="tl-meta">{fmtElapsed(it.elapsed_s)}</div>
                </>
              );
            }

            const cardClass = `tl-card ${side} ${it.role === "critic" ? "critic" : ""} ${it.ok === false ? "error" : ""}`;

            return (
              <div className="tl-turn" key={i}>
                {side === "left" && (
                  <div className={cardClass}>
                    <div className="tl-head">
                      <span>{label}</span>
                    </div>
                    {body}
                  </div>
                )}
                <div className="tl-node">
                  <span className={`dot ${dotKind}`} />
                </div>
                {side === "right" && (
                  <div className={cardClass}>
                    <div className="tl-head">
                      <span>{label}</span>
                    </div>
                    {body}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

Object.assign(window, { TraceTimeline });
