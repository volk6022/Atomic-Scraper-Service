// Variations canvas entry — wraps all variations into a DesignCanvas.

function VariationsApp() {
  // Apply muted signal by default (matches user pick)
  React.useEffect(() => {
    document.documentElement.dataset.density = "comfortable";
    document.documentElement.dataset.signal = "muted";
  }, []);

  return (
    <DesignCanvas>
      <DCSection id="intro" title="Review App · Variations"
                 subtitle="Сравнение направлений по списку и детальной карточке. CORIDOOR · моно + олива/красный сигнал.">
        <DCArtboard id="live-link" label="Live prototype" width={520} height={300}>
          <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", height: "100%", padding: 32, fontFamily: "var(--sans)", display: "flex", flexDirection: "column", justifyContent: "center", gap: 16 }}>
            <div className="label">REVIEW APP · FULL PROTOTYPE</div>
            <div style={{ fontSize: 22, fontWeight: 500, lineHeight: 1.2 }}>
              Полный flow — список, деталь, edit-mode, TTS, rerun
            </div>
            <div style={{ fontSize: 13, color: "var(--ui-fg-muted)", lineHeight: 1.5 }}>
              Открой <code style={{ color: "var(--ui-fg)", fontFamily: "var(--mono)" }}>Review App.html</code> — это направление сборки.
              Ниже на канвасе — 3 варианта списка и 3 варианта детальной карточки для сравнения.
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <a href="Review App.html" target="_blank" className="btn solid"><Icon.External /> Открыть прототип</a>
            </div>
          </div>
        </DCArtboard>
      </DCSection>

      <DCSection id="list-views" title="List views · 3 направления"
                 subtitle="Оператор просматривает 50–1000 карточек подряд. Что лучше масштабируется?">
        <DCArtboard id="list-a" label="A · Bloomberg dense ★ (live)" width={1100} height={580}>
          <ListVarA />
        </DCArtboard>
        <DCArtboard id="list-b" label="B · Split-pane preview" width={1100} height={580}>
          <ListVarB />
        </DCArtboard>
        <DCArtboard id="list-c" label="C · Card stream" width={1100} height={580}>
          <ListVarC />
        </DCArtboard>
      </DCSection>

      <DCSection id="detail-views" title="Detail views · 3 направления"
                 subtitle="Карточка + trace всегда видны. Как соотнести их пространственно?">
        <DCArtboard id="detail-a" label="A · Split right ★ (live)" width={1100} height={620}>
          <DetailVarA />
        </DCArtboard>
        <DCArtboard id="detail-b" label="B · Full-bleed + bottom drawer" width={1100} height={620}>
          <DetailVarB />
        </DCArtboard>
        <DCArtboard id="detail-c" label="C · 3-pane (queue + detail + trace)" width={1100} height={620}>
          <DetailVarC />
        </DCArtboard>
      </DCSection>

      <DCSection id="notes" title="Design system notes"
                 subtitle="Зафиксированные решения по визуальному стилю">
        <DCArtboard id="palette" label="Signal palette · muted" width={520} height={260}>
          <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", padding: 22, height: "100%", fontFamily: "var(--sans)" }}>
            <div className="label">SIGNAL PALETTE · MUTED</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginTop: 14 }}>
              <Swatch color="var(--signal-good)" name="good" hex="rgb(140,150,110)" use="pass, ≥8.5, reviewed" />
              <Swatch color="var(--signal-warn)" name="warn" hex="rgb(170,145,85)" use="6.5–8.5, edited, compact" />
              <Swatch color="var(--signal-bad)" name="bad" hex="rgb(160,70,70)" use="forced, <6.5, flagged" />
            </div>
            <div style={{ marginTop: 18, fontSize: 11, color: "var(--ui-fg-faint)", lineHeight: 1.5 }}>
              Олива и красный — из CORIDOOR (old identity). Приглушённые версии для UI-плотности. Toggle в tweaks: off → moot → default.
            </div>
          </div>
        </DCArtboard>
        <DCArtboard id="badges" label="Badge system" width={520} height={260}>
          <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", padding: 22, height: "100%", fontFamily: "var(--sans)" }}>
            <div className="label">BADGE SYSTEM</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
              <Badge kind="good" solid>PASS</Badge>
              <Badge kind="bad" solid>FORCED SUBMIT</Badge>
              <Badge kind="warn" solid>EDITED</Badge>
              <Badge kind="bad" solid>LOW SCORE</Badge>
              <Badge kind="bad" solid>EMPTY · what_they_do</Badge>
              <Badge kind="good">PASS</Badge>
              <Badge kind="bad">REJECT</Badge>
              <Badge kind="warn">COMPACT×2</Badge>
              <Badge kind="warn">RETRY×3</Badge>
              <Badge>new</Badge>
              <Badge>reviewed</Badge>
              <Badge>flagged</Badge>
            </div>
            <div style={{ marginTop: 18, fontSize: 11, color: "var(--ui-fg-faint)", lineHeight: 1.5 }}>
              Outline = деталь. Solid = состояние карточки (в заголовке). Моноширинный Fira Code · uppercase · letter-spacing 0.08em.
            </div>
          </div>
        </DCArtboard>
        <DCArtboard id="density" label="Density (compact / comfy / spacious)" width={520} height={260}>
          <div style={{ background: "var(--ui-bg)", color: "var(--ui-fg)", padding: 22, height: "100%", fontFamily: "var(--sans)" }}>
            <div className="label">DENSITY · ROW HEIGHTS</div>
            <div style={{ display: "grid", gridTemplateColumns: "60px 1fr 50px", gap: 8, marginTop: 14, fontSize: 12 }}>
              <DensityRow label="compact" h={24} />
              <DensityRow label="comfy" h={28} />
              <DensityRow label="spacious" h={36} />
            </div>
            <div style={{ marginTop: 14, fontSize: 11, color: "var(--ui-fg-faint)", lineHeight: 1.5 }}>
              Tweak `density` управляет row-h / pad-x / pad-y. По умолчанию comfortable.
            </div>
          </div>
        </DCArtboard>
      </DCSection>
    </DesignCanvas>
  );
}

function Swatch({ color, name, hex, use }) {
  return (
    <div>
      <div style={{ width: "100%", height: 32, background: color, marginBottom: 4 }} />
      <div className="mono" style={{ fontSize: 11 }}>{name}</div>
      <div className="mono faint" style={{ fontSize: 9.5, marginTop: 2 }}>{hex}</div>
      <div style={{ fontSize: 10, color: "var(--ui-fg-muted)", marginTop: 4, lineHeight: 1.4 }}>{use}</div>
    </div>
  );
}

function DensityRow({ label, h }) {
  return (
    <>
      <div className="mono" style={{ fontSize: 11, color: "var(--ui-fg-muted)" }}>{label}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={{ height: h, background: "var(--ui-bg-deep)", borderBottom: "1px solid var(--ui-border)", display: "flex", alignItems: "center", padding: "0 8px", fontSize: 11, fontFamily: "var(--mono)" }}>
            <span style={{ color: "var(--ui-fg-muted)" }}>row {i + 1}</span>
            <span style={{ flex: 1 }} />
            <span className="tabular faint">9.{i}</span>
          </div>
        ))}
      </div>
      <div className="mono faint" style={{ fontSize: 10, alignSelf: "start" }}>{h}px</div>
    </>
  );
}

const variationsRoot = ReactDOM.createRoot(document.getElementById("root"));
variationsRoot.render(<VariationsApp />);
