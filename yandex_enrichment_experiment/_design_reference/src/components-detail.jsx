// DetailView — split layout: card sections on left, trace/sources/raw on right.

function DetailView({ card, onBack, editMode, setEditMode, onPatch, onComment, comments, onToast }) {
  const [tab, setTab] = React.useState("trace");
  const [rerunOpen, setRerunOpen] = React.useState(false);
  const [rerunCtx, setRerunCtx] = React.useState("");
  const [rerunStatus, setRerunStatus] = React.useState(null); // null | queued | running | done

  function startRerun() {
    setRerunStatus("queued");
    setTimeout(() => setRerunStatus("running"), 800);
    setTimeout(() => {
      setRerunStatus("done");
      onToast?.("Ресёрч обновлён · re-ingest успешен");
      setTimeout(() => { setRerunStatus(null); setRerunOpen(false); setRerunCtx(""); }, 2200);
    }, 4500);
  }

  function markReviewed() {
    onPatch({ review_status: "reviewed" });
    onToast?.("Помечено как отрецензированную");
  }

  function flagCard() {
    onPatch({ review_status: card.review_status === "flagged" ? "new" : "flagged" });
  }

  const c = card;
  const cd = c.card || {};
  const degraded = c.forced_submit || (c.critic_score != null && c.critic_score < 6.5);
  const band = scoreBand(c.critic_score);

  return (
    <div className="detail">
      <DetailMain card={c} onBack={onBack}
                  editMode={editMode} setEditMode={setEditMode}
                  onPatch={onPatch} onComment={onComment} comments={comments}
                  markReviewed={markReviewed} flagCard={flagCard}
                  rerunOpen={rerunOpen} setRerunOpen={setRerunOpen}
                  rerunCtx={rerunCtx} setRerunCtx={setRerunCtx}
                  rerunStatus={rerunStatus} startRerun={startRerun}
                  degraded={degraded} band={band} />
      <DetailAside card={c} tab={tab} setTab={setTab} />
    </div>
  );
}

// ---------- Main column ----------

function DetailMain({ card, onBack, editMode, setEditMode, onPatch, onComment, comments, markReviewed, flagCard, rerunOpen, setRerunOpen, rerunCtx, setRerunCtx, rerunStatus, startRerun, degraded, band }) {
  const cd = card.card || {};

  function patchCard(path, value) {
    const next = JSON.parse(JSON.stringify(card.card || {}));
    // path: dot-string like "what_they_do" or "contacts.phones"
    const parts = path.split(".");
    let cur = next;
    for (let i = 0; i < parts.length - 1; i++) cur = cur[parts[i]] = cur[parts[i]] || {};
    cur[parts[parts.length - 1]] = value;
    onPatch({ card: next });
  }

  return (
    <div className="detail-main">
      <div className="detail-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 2 }}>
          <span className="btn ghost" onClick={onBack}>← список</span>
          <span className="faint mono" style={{ fontSize: 11 }}>esc</span>
          <span style={{ flex: 1 }} />
          <Toggle checked={editMode} onChange={setEditMode} label="EDIT MODE" />
          <span className="faint mono" style={{ fontSize: 11 }}>shift+E</span>
        </div>

        <div className="detail-title">
          <h1>{card.name}</h1>
          {degraded && <Badge kind="bad" solid>{card.forced_submit ? "FORCED SUBMIT" : "LOW SCORE"}</Badge>}
          {card.review_status === "edited" && <Badge kind="warn" solid>EDITED</Badge>}
          {card.review_status === "reviewed" && <Badge kind="good" solid>REVIEWED</Badge>}
          {card.review_status === "flagged" && <Badge kind="bad" solid>FLAGGED</Badge>}
          {isEmpty(cd.what_they_do) && <Badge kind="bad" solid>EMPTY · what_they_do</Badge>}
        </div>

        <div className="detail-meta mono">
          <span>oid <span className="muted">{card.oid}</span></span>
          <span>model <span className="muted">{card.model_key}</span></span>
          <span>turns <span className="muted">{card.turns}</span></span>
          <span>elapsed <span className="muted">{fmtElapsed(card.elapsed_s)}</span></span>
          <span>tokens <span className="muted">{fmtNum(card.tokens?.grand_total)}</span></span>
          <span>critic <span className={`score ${band}`}><span className="score-bar"><i style={{ width: scoreBarWidth(card.critic_score) }} /></span><span className="tabular">{card.critic_score?.toFixed(1) ?? "—"}</span></span> · <span className="muted">{card.critic_verdict || "—"}</span></span>
        </div>

        <dl className="detail-anchor">
          <dt>Адрес</dt><dd>{card.anchor?.address}</dd>
          <dt>Категории</dt><dd>{(card.anchor?.categories || []).join(", ")}</dd>
          <dt>Телефоны</dt><dd className="mono">{(card.anchor?.yandex_phones || []).join(" · ") || <span className="empty-mark">нет</span>}</dd>
          <dt>Я.Карты</dt><dd><a href={card.anchor?.yandex_url} target="_blank" rel="noreferrer">{card.anchor?.yandex_url}</a></dd>
        </dl>

        <div className="detail-actions">
          <span className="btn solid" onClick={markReviewed}><Icon.Check /> Отрецензировано</span>
          <span className="btn warn" onClick={flagCard}><Icon.Flag /> {card.review_status === "flagged" ? "Снять пометку" : "Пометить"}</span>
          <span className="btn" onClick={() => setRerunOpen(!rerunOpen)}><Icon.Rerun /> Перезапустить</span>
          <span style={{ flex: 1 }} />
          <span className="faint mono" style={{ fontSize: 10 }}>edited · {relTime()}</span>
        </div>
      </div>

      {rerunOpen && (
        <div className="rerun-panel">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span className="label">Перезапуск ресёрча с уточнением</span>
            {rerunStatus && (
              <span className="rerun-status">
                <StatusDot status={rerunStatus === "done" ? "reviewed" : "running"} />
                <span>{rerunStatus.toUpperCase()}</span>
                {rerunStatus === "running" && <span className="faint">→ агент работает…</span>}
                {rerunStatus === "done" && <span className="faint">→ карточка обновлена</span>}
              </span>
            )}
          </div>
          <textarea value={rerunCtx} onChange={(e) => setRerunCtx(e.target.value)}
                    placeholder="напр.: «не нашёл telegram-канал, проверь @advokat_fremm_spb»; «сайт fremm.ru не открывается из-за geoblock, попробуй через archive.org»"
                    disabled={rerunStatus && rerunStatus !== "done"} />
          <div style={{ display: "flex", gap: 8 }}>
            <span className="btn solid" onClick={() => !rerunStatus && startRerun()}>
              <Icon.Rerun /> {rerunStatus ? "В работе…" : "Запустить"}
            </span>
            <span className="btn ghost" onClick={() => setRerunOpen(false)}>отмена</span>
            <span style={{ flex: 1 }} />
            <span className="faint mono" style={{ fontSize: 10 }}>asyncio.Semaphore(1) · 1 GPU · сериализуется</span>
          </div>
        </div>
      )}

      <CardSections card={card} cd={cd} editMode={editMode}
                    patchCard={patchCard} comments={comments} onComment={onComment} />
    </div>
  );
}

// ---------- Card sections ----------

function CardSections({ card, cd, editMode, patchCard, comments, onComment }) {
  return (
    <>
      <Section title="What they do" anchor="wtd"
               ttsText={cd.what_they_do}
               right={editMode && <span className="faint mono" style={{ fontSize: 10 }}>{(cd.what_they_do || "").length} chars</span>}>
        <div className="wtd">
          <EditableField value={cd.what_they_do} editMode={editMode}
                         onChange={(v) => patchCard("what_they_do", v)}
                         comment={comments["what_they_do"]} onComment={(v) => onComment("what_they_do", v)} />
        </div>
      </Section>

      <Section title="Scale indicators" anchor="scale"
               ttsText={(cd.scale_indicators || []).join(". ")}>
        {cd.scale_indicators?.length > 0 ? (
          <ul className="bullets">
            {cd.scale_indicators.map((it, i) => (
              <li key={i}>
                <EditableField value={it} multiline={false} editMode={editMode}
                               onChange={(v) => {
                                 const next = [...cd.scale_indicators]; next[i] = v;
                                 patchCard("scale_indicators", next);
                               }}
                               comment={comments[`scale.${i}`]} onComment={(v) => onComment(`scale.${i}`, v)} />
              </li>
            ))}
          </ul>
        ) : <span className="empty-mark">scale_indicators пуст</span>}
      </Section>

      <Section title="Tech stack" anchor="tech">
        {cd.tech_stack?.length > 0
          ? cd.tech_stack.map((t, i) => <span key={i} className="chip">{t}</span>)
          : <span className="empty-mark">не применимо / не найдено</span>}
      </Section>

      <Section title="Contacts" anchor="contacts">
        <dl className="kv-grid">
          <dt>phones</dt>
          <dd>
            {cd.contacts?.phones?.length > 0
              ? cd.contacts.phones.map((p, i) => (
                  <div key={i} style={{ marginBottom: 4 }}>
                    <span className="mono">{p.number}</span> <span className="faint">— {p.context}</span>
                  </div>
                ))
              : <span className="empty-mark">нет</span>}
          </dd>

          <dt>emails</dt>
          <dd>
            {cd.contacts?.emails?.length > 0
              ? cd.contacts.emails.map((e, i) => (
                  <div key={i}>
                    <a href={`mailto:${e.address}`} className="mono">{e.address}</a> <span className="faint">— {e.context}</span>
                  </div>
                ))
              : <span className="empty-mark">нет</span>}
          </dd>

          <dt>websites</dt>
          <dd>
            {cd.contacts?.websites?.length > 0
              ? cd.contacts.websites.map((w, i) => (
                  <div key={i}><a href={w} target="_blank" rel="noreferrer">{w}</a> <Icon.External /></div>
                ))
              : <span className="empty-mark">нет</span>}
          </dd>
        </dl>
      </Section>

      <Section title="Social" anchor="social">
        <dl className="kv-grid">
          {["vk", "telegram", "instagram", "youtube", "linkedin", "habr"].map((k) => (
            <React.Fragment key={k}>
              <dt>{k}</dt>
              <dd>
                {cd.social?.[k]?.length > 0
                  ? cd.social[k].map((u, i) => <div key={i}><a href={u} target="_blank" rel="noreferrer">{u}</a></div>)
                  : <span className="empty-mark">—</span>}
              </dd>
            </React.Fragment>
          ))}
        </dl>
      </Section>

      <Section title="Vacancies" anchor="vacancies"
               right={<span className="faint mono" style={{ fontSize: 10 }}>{cd.vacancies?.length || 0} шт</span>}>
        {cd.vacancies?.length > 0 ? (
          <ul className="bullets" style={{ gap: 6 }}>
            {cd.vacancies.map((v, i) => (
              <li key={i}>
                <a href={v.url} target="_blank" rel="noreferrer">{v.title}</a>
                <span className="faint" style={{ marginLeft: 8 }}>· {v.platform}</span>
              </li>
            ))}
          </ul>
        ) : <span className="empty-mark">вакансий не найдено</span>}
      </Section>

      <Section title="Yandex Maps" anchor="ymaps"
               ttsText={(cd.yandex_maps?.reviews_sample || []).join(". ")}>
        <dl className="kv-grid">
          <dt>rating</dt><dd className="mono">{cd.yandex_maps?.rating ?? <span className="empty-mark">—</span>} <span className="faint">/ 5</span></dd>
          <dt>reviews</dt><dd className="mono">{cd.yandex_maps?.reviews_count ?? "—"} отзывов</dd>
          <dt>hours</dt><dd className="mono">{cd.yandex_maps?.hours || <span className="empty-mark">—</span>}</dd>
          <dt>sample</dt>
          <dd>
            {cd.yandex_maps?.reviews_sample?.length > 0
              ? cd.yandex_maps.reviews_sample.map((r, i) => (
                  <div key={i} style={{ marginBottom: 4, fontSize: 12, lineHeight: 1.4 }}>
                    <span className="faint mono">›</span> {r}
                  </div>
                ))
              : <span className="empty-mark">нет</span>}
          </dd>
        </dl>
      </Section>

      <Section title="Problems / signals" anchor="problems">
        {cd.problems_signals?.length > 0
          ? <ul className="bullets">{cd.problems_signals.map((p, i) => <li key={i} style={{ color: "var(--signal-bad)" }}>{p}</li>)}</ul>
          : <span className="empty-mark">не зафиксированы</span>}
      </Section>

      <Section title="Operator notes" anchor="notes">
        <div className="field">
          <textarea className="field-input" rows={3}
                    placeholder="Заметка ревьюера, видна только локально…"
                    defaultValue=""
                    onBlur={(e) => onComment("__operator_notes", e.target.value)} />
        </div>
      </Section>
    </>
  );
}

// ---------- Aside (right panel) ----------

function DetailAside({ card, tab, setTab }) {
  const cd = card.card || {};
  const traceLen = (card.trace || []).length;
  const sourcesLen = (cd.sources || []).length;
  const visitedLen = (card.visited_urls || []).length;
  const queriesLen = (card.queries_history || []).length;

  return (
    <div className="detail-aside">
      <div className="aside-tabs">
        <AsideTab label="Trace" count={traceLen} active={tab === "trace"} onClick={() => setTab("trace")} />
        <AsideTab label="Sources" count={sourcesLen + "/" + visitedLen} active={tab === "sources"} onClick={() => setTab("sources")} />
        <AsideTab label="Queries" count={queriesLen} active={tab === "queries"} onClick={() => setTab("queries")} />
        <AsideTab label="Tokens" active={tab === "tokens"} onClick={() => setTab("tokens")} />
        <AsideTab label="Raw" active={tab === "raw"} onClick={() => setTab("raw")} />
      </div>
      <div className="aside-body">
        {tab === "trace" && <TraceTimeline trace={card.trace} criticEvents={card.critic_events} />}
        {tab === "sources" && <SourcesPanel card={card} />}
        {tab === "queries" && <QueriesPanel queries={card.queries_history} />}
        {tab === "tokens" && <TokensPanel tokens={card.tokens} card={card} />}
        {tab === "raw" && <RawPanel obj={cd} />}
      </div>
    </div>
  );
}

function AsideTab({ label, count, active, onClick }) {
  return (
    <span className="aside-tab" aria-pressed={active} onClick={onClick}>
      {label}{count != null && <span className="count">{count}</span>}
    </span>
  );
}

function SourcesPanel({ card }) {
  const used = new Set((card.card?.sources || []).map((s) => s.url));
  const sources = card.card?.sources || [];
  const visited = card.visited_urls || [];
  const unused = visited.filter((u) => !used.has(u) && !used.has(u.replace(/\/$/, "")));
  const blocked = card.blocked_domains || [];

  return (
    <div className="source-list">
      <div style={{ padding: "10px 16px 6px", display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="label">USED · {sources.length}</span>
        <span className="faint" style={{ fontSize: 10 }}>в карточке как source</span>
      </div>
      {sources.map((s, i) => (
        <div key={i} className="source-item">
          <div>
            <div className="src-domain">{domainOf(s.url)} <Icon.External /></div>
            <div className="src-what">{s.what_it_provided}</div>
            <div><a href={s.url} target="_blank" rel="noreferrer" style={{ fontSize: 10.5 }} className="mono faint">{s.url}</a></div>
          </div>
          <div className="src-mark">used</div>
        </div>
      ))}
      <div style={{ padding: "14px 16px 6px", display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="label muted">VISITED но не использованы · {unused.length}</span>
      </div>
      {unused.map((u, i) => (
        <div key={i} className="source-item unused">
          <div>
            <div className="src-domain">{domainOf(u)}</div>
            <div className="src-what mono" style={{ fontSize: 10.5 }}>{u}</div>
          </div>
          <div className="src-mark">visited</div>
        </div>
      ))}
      {blocked.length > 0 && (
        <>
          <div style={{ padding: "14px 16px 6px" }}>
            <span className="label" style={{ color: "var(--signal-bad)" }}>BLOCKED · {blocked.length}</span>
          </div>
          {blocked.map((d, i) => (
            <div key={i} className="source-item" style={{ borderLeft: "2px solid var(--signal-bad)", marginLeft: 0 }}>
              <div><div className="src-domain" style={{ color: "var(--signal-bad)" }}>{d}</div>
                <div className="src-what">домен заблокирован после {">2"} ошибок</div>
              </div>
              <div className="src-mark">blocked</div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function QueriesPanel({ queries }) {
  if (!queries?.length) return <div style={{ padding: 16, color: "var(--ui-fg-faint)" }}>Пусто</div>;
  return (
    <div className="queries">
      {queries.map((q, i) => (
        <div key={i} className="q">
          <span className="idx">{String(i + 1).padStart(2, "0")}</span>
          <span><Icon.Search /> {q}</span>
        </div>
      ))}
    </div>
  );
}

function TokensPanel({ tokens, card }) {
  if (!tokens) return <div style={{ padding: 16, color: "var(--ui-fg-faint)" }}>—</div>;
  return (
    <div className="tokens-grid">
      <div className="tokens-card">
        <div className="label">MAIN · prompt</div>
        <div className="v">{fmtNum(tokens.main?.prompt)}</div>
      </div>
      <div className="tokens-card">
        <div className="label">MAIN · completion</div>
        <div className="v">{fmtNum(tokens.main?.completion)}</div>
      </div>
      <div className="tokens-card">
        <div className="label">AUX · critic+refraser</div>
        <div className="v">{fmtNum((tokens.aux?.prompt || 0) + (tokens.aux?.completion || 0))}</div>
      </div>
      <div className="tokens-card">
        <div className="label">GRAND TOTAL</div>
        <div className="v" style={{ color: tokens.grand_total > 100000 ? "var(--signal-warn)" : "var(--ui-fg)" }}>
          {fmtNum(tokens.grand_total)}
        </div>
      </div>
      <div className="tokens-card" style={{ gridColumn: "1 / -1" }}>
        <div className="label">TOOL CALLS</div>
        <div className="mono" style={{ fontSize: 12, marginTop: 6 }}>
          web_serp <span className="tabular muted">{card.tool_call_counts?.web_serp}</span>{"  "}
          web_scrape <span className="tabular muted">{card.tool_call_counts?.web_scrape}</span>{"  "}
          submit <span className="tabular muted">{card.tool_call_counts?.submit_org_card}</span>{"  "}
          refraser <span className="tabular muted">{card.refraser_runs}</span>{"  "}
          compactions <span className="tabular muted">{card.compactions}</span>
        </div>
      </div>
    </div>
  );
}

function RawPanel({ obj }) {
  return (
    <pre className="raw-editor" dangerouslySetInnerHTML={{ __html: jsonHighlight(obj) }} />
  );
}

Object.assign(window, { DetailView });
