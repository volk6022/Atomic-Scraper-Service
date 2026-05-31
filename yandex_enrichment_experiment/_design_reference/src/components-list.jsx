// ListView — dense Bloomberg-style table with filter tabs + keyboard nav.

function ListView({ cards, selectedOid, onSelect, search, setSearch, statusFilter, setStatusFilter, sortKey, setSortKey, sortDir, setSortDir }) {
  const tableRef = React.useRef(null);

  // Filtering
  const filtered = React.useMemo(() => {
    let rows = cards.slice();
    if (statusFilter === "need_review") {
      rows = rows.filter((c) => c.review_status === "new" || c.review_status === "flagged" || (c.critic_score != null && c.critic_score < 7) || c.forced_submit);
    } else if (statusFilter !== "all") {
      rows = rows.filter((c) => c.review_status === statusFilter);
    }
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter((c) =>
        (c.name || "").toLowerCase().includes(q) ||
        (c.anchor?.address || "").toLowerCase().includes(q) ||
        (c.card?.what_they_do || "").toLowerCase().includes(q) ||
        c.oid.includes(q)
      );
    }
    rows.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return rows;
  }, [cards, statusFilter, search, sortKey, sortDir]);

  // Keyboard nav: ↑/↓ to move selection, Enter to open
  React.useEffect(() => {
    const onKey = (e) => {
      if (e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
      const idx = filtered.findIndex((c) => c.oid === selectedOid);
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        const next = filtered[Math.min(filtered.length - 1, idx + 1)];
        if (next) onSelect(next.oid, { focus: false });
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        const next = filtered[Math.max(0, idx - 1)];
        if (next) onSelect(next.oid, { focus: false });
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (selectedOid) onSelect(selectedOid, { focus: true });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filtered, selectedOid, onSelect]);

  // Auto-scroll selected into view
  React.useEffect(() => {
    if (!tableRef.current || !selectedOid) return;
    const el = tableRef.current.querySelector(`tr[data-oid="${selectedOid}"]`);
    if (!el) return;
    const container = tableRef.current;
    const r = el.getBoundingClientRect();
    const cr = container.getBoundingClientRect();
    if (r.top < cr.top + 40) container.scrollTop += r.top - cr.top - 40;
    else if (r.bottom > cr.bottom - 10) container.scrollTop += r.bottom - cr.bottom + 10;
  }, [selectedOid]);

  function header(label, key, width) {
    const active = sortKey === key;
    return (
      <th style={width ? { width } : undefined} onClick={() => {
        if (key) {
          if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
          else { setSortKey(key); setSortDir("desc"); }
        }
      }}>
        {label}{active && <span style={{ marginLeft: 4 }}>{sortDir === "asc" ? "↑" : "↓"}</span>}
      </th>
    );
  }

  const counts = React.useMemo(() => {
    const c = { all: cards.length, new: 0, reviewed: 0, flagged: 0, edited: 0, need_review: 0 };
    cards.forEach((x) => {
      c[x.review_status] = (c[x.review_status] || 0) + 1;
      if (x.review_status === "new" || x.review_status === "flagged" || (x.critic_score != null && x.critic_score < 7) || x.forced_submit) c.need_review += 1;
    });
    return c;
  }, [cards]);

  return (
    <div className="listview">
      <div className="list-filters">
        <FilterTab label="Нужно ревью" count={counts.need_review} active={statusFilter === "need_review"} onClick={() => setStatusFilter("need_review")} flag />
        <FilterTab label="Все" count={counts.all} active={statusFilter === "all"} onClick={() => setStatusFilter("all")} />
        <FilterTab label="Новые" count={counts.new || 0} active={statusFilter === "new"} onClick={() => setStatusFilter("new")} />
        <FilterTab label="Отрецензированы" count={counts.reviewed || 0} active={statusFilter === "reviewed"} onClick={() => setStatusFilter("reviewed")} />
        <FilterTab label="Отредактированы" count={counts.edited || 0} active={statusFilter === "edited"} onClick={() => setStatusFilter("edited")} />
        <FilterTab label="С пометкой" count={counts.flagged || 0} active={statusFilter === "flagged"} onClick={() => setStatusFilter("flagged")} />
      </div>

      <div className="list-toolbar">
        <span className="muted">{filtered.length} карточек</span>
        <span className="faint">·</span>
        <span className="faint">пагинация: 50 / стр. (sample)</span>
        <span style={{ flex: 1 }} />
        <span className="faint">сортировка</span>
        <select value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
          <option value="critic_score">critic score</option>
          <option value="elapsed_s">elapsed</option>
          <option value="tokens.grand_total">tokens</option>
          <option value="turns">turns</option>
          <option value="name">name</option>
        </select>
        <span className="faint">·</span>
        <span className="faint mono">↑↓ навигация · Enter открыть · / поиск</span>
      </div>

      <div className="table" ref={tableRef}>
        <table>
          <thead>
            <tr>
              {header("", null, 18)}
              {header("ORG NAME", "name")}
              {header("ADDRESS", null)}
              {header("CATEGORIES", null)}
              {header("CRITIC", "critic_score", 80)}
              {header("VERDICT", null, 70)}
              {header("FLAGS", null, 110)}
              {header("TURNS", "turns", 60)}
              {header("TOKENS", "tokens.grand_total", 70)}
              {header("ELAPSED", "elapsed_s", 70)}
              {header("STATUS", "review_status", 90)}
              {header("UPDATED", null, 70)}
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => {
              const sel = c.oid === selectedOid;
              const degraded = c.forced_submit || (c.critic_score != null && c.critic_score < 6.5);
              const reviewed = c.review_status === "reviewed";
              const edited = c.review_status === "edited";
              return (
                <tr key={c.oid} data-oid={c.oid}
                    className={[sel ? "selected" : "", degraded ? "degraded" : "", reviewed ? "reviewed" : "", edited ? "edited" : ""].join(" ").trim()}
                    onClick={() => onSelect(c.oid, { focus: false })}
                    onDoubleClick={() => onSelect(c.oid, { focus: true })}>
                  <td className="col-status"><StatusDot status={c.review_status} /></td>
                  <td className="col-name">
                    {c.name}
                    <span className="sub mono">{c.oid}</span>
                  </td>
                  <td className="col-cats" title={c.anchor?.address}>{c.anchor?.address?.replace("Санкт-Петербург, ", "") || "—"}</td>
                  <td className="col-cats">{(c.anchor?.categories || []).slice(0, 2).join(" · ")}</td>
                  <td className="col-score"><Score value={c.critic_score} /></td>
                  <td><Badge kind={c.critic_verdict === "pass" ? "good" : "bad"}>{c.critic_verdict || "—"}</Badge></td>
                  <td>
                    {c.forced_submit && <Badge kind="bad">FORCED</Badge>}
                    {c.compactions > 0 && <Badge kind="warn">COMPACT×{c.compactions}</Badge>}
                    {c.submit_attempts > 1 && <Badge kind="warn">RETRY×{c.submit_attempts}</Badge>}
                    {isEmpty(c.card?.what_they_do) && <Badge kind="bad">EMPTY</Badge>}
                  </td>
                  <td className="col-num">{c.turns}</td>
                  <td className="col-num">{fmtNum(c.tokens?.grand_total)}</td>
                  <td className="col-num">{fmtElapsed(c.elapsed_s)}</td>
                  <td><Badge>{c.review_status}</Badge></td>
                  <td className="col-num faint">{relTime()}</td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={12} style={{ padding: 40, textAlign: "center", color: "var(--ui-fg-faint)" }}>Нет карточек по этому фильтру</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FilterTab({ label, count, active, onClick, flag }) {
  return (
    <span className={`list-filter-tab ${flag ? "flag" : ""}`} aria-pressed={active} onClick={onClick}>
      {label}<span className="count">{count}</span>
    </span>
  );
}

Object.assign(window, { ListView });
