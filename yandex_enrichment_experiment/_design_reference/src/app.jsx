// App shell — sidebar rail, top bar, list/detail switching, tweaks panel.

function App() {
  const [t, setTweak] = useTweaks({
    density: "comfortable",
    fontStyle: "sans",
    signalIntensity: "muted",
    showKbdHints: true,
    autoOpenOnHover: false,
  });

  const [cards, setCards] = React.useState(window.MOCK_CARDS);
  const [selectedOid, setSelectedOid] = React.useState(cards[0]?.oid);
  const [openOid, setOpenOid] = React.useState(null); // null = list view
  const [statusFilter, setStatusFilter] = React.useState("all");
  const [search, setSearch] = React.useState("");
  const [sortKey, setSortKey] = React.useState("critic_score");
  const [sortDir, setSortDir] = React.useState("asc");
  const [editMode, setEditMode] = React.useState(false);
  const [comments, setComments] = React.useState({});
  const [toast, setToast] = React.useState(null);

  // Apply tweaks to root
  React.useEffect(() => {
    const root = document.documentElement;
    root.dataset.density = t.density;
    root.dataset.font = t.fontStyle === "mono" ? "mono" : "";
    root.dataset.signal = t.signalIntensity;
  }, [t.density, t.fontStyle, t.signalIntensity]);

  // Keyboard shortcuts
  React.useEffect(() => {
    const onKey = (e) => {
      if (e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) {
        if (e.key === "Escape") e.target.blur();
        return;
      }
      if (e.key === "Escape" && openOid) { setOpenOid(null); }
      else if (e.key === "Enter" && !openOid && selectedOid) { setOpenOid(selectedOid); }
      else if (e.key === "E" && e.shiftKey) { setEditMode((v) => !v); }
      else if (e.key === "/") { e.preventDefault(); document.getElementById("topbar-search")?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openOid, selectedOid]);

  function handleSelect(oid, opts) {
    setSelectedOid(oid);
    if (opts?.focus) setOpenOid(oid);
  }

  function patchCard(patch) {
    setCards((cs) => cs.map((c) => c.oid === openOid ? { ...c, ...patch, review_status: patch.card ? "edited" : (patch.review_status || c.review_status) } : c));
  }

  function setComment(field, val) {
    setComments((m) => {
      const k = `${openOid}::${field}`;
      const n = { ...m };
      if (!val || val.trim() === "") delete n[k]; else n[k] = val;
      return n;
    });
  }

  const cardComments = React.useMemo(() => {
    const r = {};
    Object.entries(comments).forEach(([k, v]) => {
      const [oid, f] = k.split("::");
      if (oid === openOid) r[f] = v;
    });
    return r;
  }, [comments, openOid]);

  const openCard = cards.find((c) => c.oid === openOid);
  const counts = React.useMemo(() => {
    const c = { all: cards.length, new: 0, reviewed: 0, edited: 0, flagged: 0, need_review: 0 };
    cards.forEach((x) => {
      c[x.review_status] = (c[x.review_status] || 0) + 1;
      if (x.review_status === "new" || x.review_status === "flagged" || (x.critic_score != null && x.critic_score < 7) || x.forced_submit) c.need_review += 1;
    });
    return c;
  }, [cards]);

  return (
    <div className="app">
      <Rail counts={counts} statusFilter={statusFilter} setStatusFilter={(s) => { setStatusFilter(s); setOpenOid(null); }} />

      <div className="main">
        <TopBar openCard={openCard} onHome={() => setOpenOid(null)}
                search={search} setSearch={setSearch} />

        {openCard
          ? <DetailView card={openCard}
                        onBack={() => setOpenOid(null)}
                        editMode={editMode} setEditMode={setEditMode}
                        onPatch={patchCard}
                        comments={cardComments}
                        onComment={setComment}
                        onToast={setToast} />
          : <ListView cards={cards} selectedOid={selectedOid}
                      onSelect={(oid, opts) => {
                        handleSelect(oid, opts);
                        if (opts?.focus) setOpenOid(oid);
                      }}
                      search={search} setSearch={setSearch}
                      statusFilter={statusFilter} setStatusFilter={setStatusFilter}
                      sortKey={sortKey} setSortKey={setSortKey}
                      sortDir={sortDir} setSortDir={setSortDir} />}
      </div>

      <Toast msg={toast} onDone={() => setToast(null)} />

      <TweaksPanel>
        <TweakSection label="Density" />
        <TweakRadio label="Плотность" value={t.density}
                    options={["compact", "comfortable", "spacious"]}
                    onChange={(v) => setTweak("density", v)} />

        <TweakSection label="Typography" />
        <TweakRadio label="Шрифт" value={t.fontStyle}
                    options={["sans", "mono"]}
                    onChange={(v) => setTweak("fontStyle", v)} />
        <TweakRow label="" hint="sans = Roboto Condensed (DS) · mono = Fira Code" />

        <TweakSection label="Signal color" />
        <TweakRadio label="Интенсивность" value={t.signalIntensity}
                    options={["off", "muted", "default"]}
                    onChange={(v) => setTweak("signalIntensity", v)} />
        <TweakRow label="" hint="off = чистый CORIDOOR mono · muted = приглушённые · default = яркие" />

        <TweakSection label="Keyboard" />
        <TweakToggle label="Показывать подсказки клавиш" value={t.showKbdHints}
                     onChange={(v) => setTweak("showKbdHints", v)} />

        <TweakSection label="Действия" />
        <TweakButton label="Сбросить статусы" onClick={() => {
          setCards(window.MOCK_CARDS);
          setComments({});
          setToast("State сброшен");
        }} />
        <TweakButton label="Открыть variations canvas" onClick={() => {
          window.open("Variations.html", "_blank");
        }} />
      </TweaksPanel>
    </div>
  );
}

function Rail({ counts, statusFilter, setStatusFilter }) {
  const RailItem = ({ id, label, count }) => (
    <div className="rail-item" aria-current={statusFilter === id} onClick={() => setStatusFilter(id)}>
      <span>{label}</span><span className="rail-item-count">{count}</span>
    </div>
  );
  return (
    <aside className="rail">
      <div className="rail-brand">
        <span className="rail-brand-dot" />
        <span className="rail-brand-mark">RESEARCH · REVIEW</span>
      </div>

      <div className="rail-section">
        <div className="rail-section-title">QUEUE</div>
        <RailItem id="need_review" label="Нужно ревью" count={counts.need_review} />
        <RailItem id="all" label="Все карточки" count={counts.all} />
      </div>

      <div className="rail-section">
        <div className="rail-section-title">STATUS</div>
        <RailItem id="new" label="Новые" count={counts.new || 0} />
        <RailItem id="reviewed" label="Отрецензированы" count={counts.reviewed || 0} />
        <RailItem id="edited" label="Отредактированы" count={counts.edited || 0} />
        <RailItem id="flagged" label="С пометкой" count={counts.flagged || 0} />
      </div>

      <div className="rail-section">
        <div className="rail-section-title">BATCHES</div>
        <div className="rail-item"><span>batch-2026-05-28 (500)</span><span className="rail-item-count mono">68%</span></div>
        <div className="rail-item"><span>batch-2026-05-27 (412)</span><span className="rail-item-count mono">DONE</span></div>
      </div>

      <div className="rail-footer">
        <div>local · 127.0.0.1:8002</div>
        <div>postgres · 14·jsonb</div>
        <div>1 GPU · agent_runner idle</div>
      </div>
    </aside>
  );
}

function TopBar({ openCard, onHome, search, setSearch }) {
  return (
    <header className="topbar">
      <div className="crumb">
        <span onClick={onHome} style={{ cursor: "pointer" }}>review</span>
        <span className="crumb-sep">›</span>
        {openCard
          ? <><span>cards</span><span className="crumb-sep">›</span><span className="crumb-current">{openCard.name}</span></>
          : <span className="crumb-current">cards</span>}
      </div>

      <div className="topbar-search">
        <Icon.Search />
        <input id="topbar-search" value={search} onChange={(e) => setSearch(e.target.value)}
               placeholder="поиск по name / address / what_they_do / oid    /" />
      </div>

      <div className="topbar-meta">
        <span className="pill">v2.1 local</span>
        <span>1000341388__local.json</span>
      </div>
    </header>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
