// Variation A — List: Bloomberg dense table (matches the live prototype, mini-rendered)
// Static rendering with same look + a fixed subset of data.

const VAR_DATA = window.MOCK_CARDS;

// ============================================================
// LIST VIEW VARIATIONS
// ============================================================

function ListVarA() {
  // Bloomberg dense — current direction
  return (
    <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", fontFamily: "var(--sans)", display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="list-filters" style={{ borderTop: "none", flexShrink: 0 }}>
        <FilterTab label="Нужно ревью" count={9} active flag />
        <FilterTab label="Все" count={12} />
        <FilterTab label="Новые" count={7} />
        <FilterTab label="Reviewed" count={2} />
      </div>
      <div className="list-toolbar" style={{ flexShrink: 0 }}>
        <span className="muted">12 карточек</span>
        <span className="faint">·</span>
        <span className="faint">sort: critic ↑</span>
        <span style={{ flex: 1 }} />
        <span className="faint mono">↑↓ Enter /</span>
      </div>
      <div className="table" style={{ flex: 1 }}>
        <table>
          <thead>
            <tr>
              <th style={{ width: 16 }}></th>
              <th>ORG NAME</th>
              <th>ADDRESS</th>
              <th style={{ width: 80 }}>CRITIC</th>
              <th style={{ width: 70 }}>VERDICT</th>
              <th style={{ width: 110 }}>FLAGS</th>
              <th style={{ width: 60 }}>TURNS</th>
              <th style={{ width: 70 }}>TOKENS</th>
              <th style={{ width: 90 }}>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {VAR_DATA.slice(0, 8).map((c) => {
              const degraded = c.forced_submit || (c.critic_score < 6.5);
              return (
                <tr key={c.oid} className={degraded ? "degraded" : ""}>
                  <td className="col-status"><StatusDot status={c.review_status} /></td>
                  <td className="col-name">{c.name}<span className="sub mono">{c.oid.slice(-6)}</span></td>
                  <td className="col-cats">{c.anchor.address?.replace("Санкт-Петербург, ", "").slice(0, 30)}</td>
                  <td className="col-score"><Score value={c.critic_score} /></td>
                  <td><Badge kind={c.critic_verdict === "pass" ? "good" : "bad"}>{c.critic_verdict}</Badge></td>
                  <td>{c.forced_submit && <Badge kind="bad">FORCED</Badge>}{c.compactions > 0 && <Badge kind="warn">CMPCT</Badge>}</td>
                  <td className="col-num">{c.turns}</td>
                  <td className="col-num">{fmtNum(c.tokens.grand_total)}</td>
                  <td><Badge>{c.review_status}</Badge></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ListVarB() {
  // 3-pane: filter rail | dense rows | preview
  const sel = VAR_DATA[7]; // Адвокат Фремм
  return (
    <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", fontFamily: "var(--sans)", display: "grid", gridTemplateColumns: "260px 1fr", height: "100%" }}>
      <div style={{ borderRight: "1px solid var(--ui-border)", overflow: "hidden" }}>
        <div className="list-filters" style={{ borderTop: "none" }}>
          <FilterTab label="Нужно ревью" count={9} active flag />
        </div>
        <div style={{ overflow: "auto", height: "calc(100% - 32px)" }}>
          {VAR_DATA.slice(0, 9).map((c, i) => {
            const sel2 = c.oid === sel.oid;
            return (
              <div key={c.oid} style={{ padding: "8px 12px", borderBottom: "1px solid var(--ui-border)",
                                          background: sel2 ? "var(--ui-bg-active)" : "transparent",
                                          boxShadow: sel2 ? "inset 2px 0 0 var(--signal-good)" : (c.forced_submit ? "inset 2px 0 0 var(--signal-bad)" : "none"),
                                          opacity: c.review_status === "reviewed" ? 0.55 : 1 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                  <StatusDot status={c.review_status} />
                  <span style={{ flex: 1, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                  <Score value={c.critic_score} />
                </div>
                <div className="mono" style={{ fontSize: 10.5, color: "var(--ui-fg-faint)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.oid} · {c.turns}t · {fmtNum(c.tokens.grand_total)}
                </div>
                <div style={{ fontSize: 11, color: "var(--ui-fg-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.anchor.address?.replace("Санкт-Петербург, ", "")}
                </div>
                {c.forced_submit && <div style={{ marginTop: 4 }}><Badge kind="bad">FORCED</Badge></div>}
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ overflow: "auto", padding: "20px 24px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 500 }}>{sel.name}</h2>
          <Score value={sel.critic_score} />
          <Badge kind="good" solid>PASS</Badge>
        </div>
        <div className="mono" style={{ fontSize: 11, color: "var(--ui-fg-muted)", marginTop: 6 }}>
          {sel.oid} · {sel.anchor.address}
        </div>
        <div style={{ marginTop: 16, fontSize: 14, lineHeight: 1.5, color: "var(--ui-fg)" }}>
          {sel.card.what_they_do}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 24 }}>
          <div>
            <div className="label">CONTACTS</div>
            <div style={{ marginTop: 6, fontSize: 12 }}>
              {sel.card.contacts.phones.map((p, i) => <div key={i} className="mono">{p.number}</div>)}
              {sel.card.contacts.websites.map((w, i) => <div key={i}><a href={w}>{domainOf(w)}</a></div>)}
            </div>
          </div>
          <div>
            <div className="label">SOCIAL</div>
            <div style={{ marginTop: 6, fontSize: 12 }}>
              {sel.card.social.vk.map((u, i) => <div key={i}>vk · {domainOf(u)}{u.slice(u.indexOf("vk.com") + 6)}</div>)}
            </div>
          </div>
        </div>
        <div style={{ marginTop: 20, display: "flex", gap: 8 }}>
          <span className="btn solid"><Icon.Check /> Отрецензировано</span>
          <span className="btn"><Icon.External /> Открыть полную</span>
        </div>
      </div>
    </div>
  );
}

function ListVarC() {
  // Card stream: rich rows with what_they_do preview
  return (
    <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", fontFamily: "var(--sans)", overflow: "auto", height: "100%" }}>
      <div className="list-filters" style={{ borderTop: "none", position: "sticky", top: 0, background: "var(--ui-bg)", zIndex: 1 }}>
        <FilterTab label="Нужно ревью" count={9} active flag />
        <FilterTab label="Все" count={12} />
      </div>
      <div style={{ padding: "0 4px" }}>
        {VAR_DATA.slice(0, 6).map((c) => {
          const degraded = c.forced_submit || (c.critic_score < 6.5);
          return (
            <div key={c.oid} style={{
              display: "grid",
              gridTemplateColumns: "1fr 220px",
              gap: 18,
              padding: "16px 18px",
              borderBottom: "1px solid var(--ui-border)",
              borderLeft: degraded ? "2px solid var(--signal-bad)" : "2px solid transparent",
              opacity: c.review_status === "reviewed" ? 0.55 : 1,
            }}>
              <div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                  <StatusDot status={c.review_status} />
                  <span style={{ fontSize: 15 }}>{c.name}</span>
                  <span className="mono faint" style={{ fontSize: 10.5 }}>{c.oid}</span>
                  {c.forced_submit && <Badge kind="bad" solid>FORCED</Badge>}
                  {isEmpty(c.card.what_they_do) && <Badge kind="bad">EMPTY</Badge>}
                </div>
                <div style={{ fontSize: 12, color: "var(--ui-fg-muted)", marginTop: 4 }}>
                  {c.anchor.address?.replace("Санкт-Петербург, ", "")} · {c.anchor.categories.slice(0, 2).join(" · ")}
                </div>
                <div style={{ fontSize: 13, color: "var(--ui-fg)", marginTop: 8, lineHeight: 1.4,
                              maxHeight: 36, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box",
                              WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                  {c.card.what_they_do || <span className="empty-mark">what_they_do пусто</span>}
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                <Score value={c.critic_score} />
                <div className="mono" style={{ fontSize: 10.5, color: "var(--ui-fg-muted)" }}>
                  {c.turns}t · {fmtNum(c.tokens.grand_total)}tok · {fmtElapsed(c.elapsed_s)}
                </div>
                <Badge>{c.review_status}</Badge>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// DETAIL VIEW VARIATIONS
// ============================================================

function DetailVarA() {
  // Current direction — split with right trace panel (compact)
  const c = VAR_DATA[0];
  return (
    <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", fontFamily: "var(--sans)", display: "grid", gridTemplateColumns: "1fr 360px", height: "100%" }}>
      <div style={{ overflow: "auto", borderRight: "1px solid var(--ui-border)" }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--ui-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
            <span className="btn ghost">←</span><span className="faint">esc</span>
            <span style={{ flex: 1 }} />
            <Toggle checked={false} onChange={() => {}} label="EDIT" />
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 8 }}>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 500 }}>{c.name}</h1>
            <Score value={c.critic_score} />
            <Badge kind="good" solid>PASS</Badge>
          </div>
          <div className="detail-meta mono" style={{ marginTop: 6 }}>
            <span>oid {c.oid}</span><span>turns {c.turns}</span><span>{fmtElapsed(c.elapsed_s)}</span><span>{fmtNum(c.tokens.grand_total)} tok</span>
          </div>
          <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
            <span className="btn solid" style={{ fontSize: 10 }}><Icon.Check /> Reviewed</span>
            <span className="btn" style={{ fontSize: 10 }}><Icon.Rerun /> Перезапустить</span>
          </div>
        </div>
        <div className="section">
          <div className="section-head"><h2>What they do</h2><div className="tools"><TTSButton text={c.card.what_they_do} /></div></div>
          <div style={{ fontSize: 13, lineHeight: 1.5 }}>{c.card.what_they_do}</div>
        </div>
        <div className="section">
          <div className="section-head"><h2>Scale</h2></div>
          <ul className="bullets">{c.card.scale_indicators.slice(0, 3).map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      </div>
      <div style={{ background: "var(--ui-bg-deep)", display: "grid", gridTemplateRows: "auto 1fr", overflow: "hidden" }}>
        <div className="aside-tabs">
          <span className="aside-tab" aria-pressed>Trace<span className="count">26</span></span>
          <span className="aside-tab">Sources<span className="count">8</span></span>
          <span className="aside-tab">Raw</span>
        </div>
        <div style={{ overflow: "auto" }}><TraceTimeline trace={c.trace} /></div>
      </div>
    </div>
  );
}

function DetailVarB() {
  // Full-bleed with trace as a collapsible bottom drawer (currently expanded)
  const c = VAR_DATA[0];
  return (
    <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", fontFamily: "var(--sans)", display: "grid", gridTemplateRows: "1fr 240px", height: "100%" }}>
      <div style={{ overflow: "auto", padding: "20px 32px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 500 }}>{c.name}</h1>
          <Score value={c.critic_score} />
          <Badge kind="good" solid>PASS · 9.0</Badge>
        </div>
        <div className="detail-meta mono" style={{ marginTop: 8 }}>
          <span>oid {c.oid}</span><span>{c.anchor.address}</span><span>turns {c.turns}</span><span>{fmtNum(c.tokens.grand_total)} tok</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, marginTop: 24 }}>
          <div>
            <div className="label">WHAT THEY DO</div>
            <div style={{ fontSize: 14, lineHeight: 1.5, marginTop: 8 }}>{c.card.what_they_do}</div>
          </div>
          <div>
            <div className="label">SCALE INDICATORS</div>
            <ul className="bullets" style={{ marginTop: 8 }}>{c.card.scale_indicators.map((s, i) => <li key={i}>{s}</li>)}</ul>
            <div className="label" style={{ marginTop: 16 }}>CONTACTS</div>
            <div className="mono" style={{ marginTop: 8, fontSize: 12 }}>
              {c.card.contacts.phones.map((p, i) => <div key={i}>{p.number}</div>)}
              {c.card.contacts.websites.map((w, i) => <div key={i}><a href={w}>{w}</a></div>)}
            </div>
          </div>
        </div>
      </div>
      <div style={{ background: "var(--ui-bg-deep)", borderTop: "1px solid var(--ui-border-strong)", overflow: "hidden", display: "grid", gridTemplateRows: "auto 1fr" }}>
        <div style={{ padding: "8px 16px", display: "flex", alignItems: "center", gap: 12, borderBottom: "1px solid var(--ui-border)" }}>
          <span className="label">TRACE · 26 events</span>
          <span className="faint mono" style={{ fontSize: 10 }}>15 turns · 1 critic · 0 refraser</span>
          <span style={{ flex: 1 }} />
          <span className="btn ghost" style={{ fontSize: 10 }}>↓ свернуть</span>
        </div>
        <div style={{ overflow: "auto", padding: "8px 16px", display: "flex", gap: 8, alignItems: "stretch" }}>
          {c.trace.slice(0, 8).map((t, i) => (
            <div key={i} style={{
              minWidth: 180, padding: "6px 10px", border: "1px solid var(--ui-border)",
              background: t.role === "tool" && t.ok === false ? "var(--signal-bad-dim)" : "transparent",
              fontSize: 11,
            }}>
              <div className="mono faint" style={{ fontSize: 10 }}>T{t.turn} · {t.role}</div>
              <div className="mono" style={{ fontSize: 11, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.tool}</div>
              <div style={{ fontSize: 10, color: "var(--ui-fg-muted)", marginTop: 2 }}>{fmtElapsed(t.elapsed_s)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DetailVarC() {
  // 3-pane: micro-list | detail | trace
  const c = VAR_DATA[0];
  return (
    <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", fontFamily: "var(--sans)", display: "grid", gridTemplateColumns: "180px 1fr 300px", height: "100%" }}>
      {/* Micro list */}
      <div style={{ borderRight: "1px solid var(--ui-border)", overflow: "auto", background: "var(--ui-bg-deep)" }}>
        <div className="label" style={{ padding: "8px 10px" }}>QUEUE · 9</div>
        {VAR_DATA.slice(0, 9).map((x) => (
          <div key={x.oid} style={{
            padding: "6px 10px", borderBottom: "1px solid var(--ui-border)",
            background: x.oid === c.oid ? "var(--ui-bg-active)" : "transparent",
            boxShadow: x.oid === c.oid ? "inset 2px 0 0 var(--signal-good)" : "none",
            fontSize: 11,
          }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
              <StatusDot status={x.review_status} />
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.name}</span>
              <span className="mono tabular" style={{ fontSize: 10, color: "var(--ui-fg-muted)" }}>{x.critic_score?.toFixed(1)}</span>
            </div>
          </div>
        ))}
      </div>
      {/* Detail */}
      <div style={{ overflow: "auto" }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--ui-border)" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 500 }}>{c.name}</h2>
            <Score value={c.critic_score} />
          </div>
          <div className="mono faint" style={{ fontSize: 10.5, marginTop: 4 }}>{c.oid} · {c.anchor.address}</div>
        </div>
        <div style={{ padding: "16px 18px" }}>
          <div className="label">WHAT THEY DO</div>
          <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 6 }}>{c.card.what_they_do}</div>
          <div className="label" style={{ marginTop: 16 }}>SCALE</div>
          <ul className="bullets" style={{ marginTop: 6 }}>{c.card.scale_indicators.slice(0, 3).map((s, i) => <li key={i}>{s}</li>)}</ul>
          <div className="label" style={{ marginTop: 16 }}>CONTACTS</div>
          <div className="mono" style={{ marginTop: 6, fontSize: 12 }}>
            {c.card.contacts.phones.map((p, i) => <div key={i}>{p.number}</div>)}
          </div>
        </div>
      </div>
      {/* Trace */}
      <div style={{ background: "var(--ui-bg-deep)", borderLeft: "1px solid var(--ui-border)", overflow: "hidden", display: "grid", gridTemplateRows: "auto 1fr" }}>
        <div className="label" style={{ padding: "8px 10px" }}>TRACE · 26</div>
        <div style={{ overflow: "auto" }}>
          {c.trace.slice(0, 14).map((t, i) => (
            <div key={i} style={{ padding: "4px 10px", borderBottom: "1px solid var(--ui-border)", fontSize: 10.5, fontFamily: "var(--mono)" }}>
              <span className="faint">T{String(t.turn).padStart(2, "0")}</span>{" "}
              <span style={{ color: t.role === "tool" && t.ok === false ? "var(--signal-bad)" : "var(--ui-fg-muted)" }}>{t.tool || t.role}</span>
              {t.elapsed_s && <span className="faint"> · {fmtElapsed(t.elapsed_s)}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ListVarA, ListVarB, ListVarC, DetailVarA, DetailVarB, DetailVarC });
