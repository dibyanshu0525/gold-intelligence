import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3, Bell,
  CheckCircle2, ChevronDown, Clock3, Coins, Database, ExternalLink,
  Gauge, Globe2, Landmark, RefreshCw, Settings2, ShieldCheck, SlidersHorizontal,
  Sparkles, TrendingDown, TrendingUp, Wallet, X, Zap,
} from 'lucide-react'
import {
  Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import RetailerBoard from './RetailerBoard.jsx'

const API = import.meta.env.VITE_API_URL || ''

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

const inr = (value, digits = 0) => value == null || !Number.isFinite(Number(value))
  ? '—'
  : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(Number(value))
const usd = (value) => value == null || !Number.isFinite(Number(value)) ? '—' : `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })}`
const pct = (value, digits = 2) => value == null || !Number.isFinite(Number(value)) ? '—' : `${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(digits)}%`
const fmtTime = (value) => {
  if (!value) return 'Timestamp unavailable'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? 'Timestamp unavailable' : d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
const num = (value, digits = 2) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('en-IN', { maximumFractionDigits: digits })

function StatusPill({ status }) {
  const kind = status === 'live' ? 'live' : status === 'manual' ? 'manual' : status === 'delayed' ? 'delayed' : status === 'stale' ? 'stale' : 'offline'
  const label = status === 'live' ? 'LIVE FEED' : status === 'manual' ? 'MANUAL' : status === 'delayed' ? 'PUBLISHED / DELAYED' : status === 'stale' ? 'STALE CACHE' : 'UNAVAILABLE'
  return <span className={`status-pill ${kind}`}><i />{label}</span>
}

function ProviderHealthCard({ id, provider }) {
  const labels = {
    xaus: 'XAUS · live spot + FX', gold_api_com: 'Gold-API.com · keyless live', goldapi_dev: 'GoldAPI.dev · live cross-check',
    goldprice_dev: 'GoldPrice.dev · 15m delayed', frankfurter_fx: 'Frankfurter · daily FX',
    twelve_data_fx: 'Twelve Data · FX backup', metals_dev: 'Metals.Dev · optional legacy',
    ibja_public: 'IBJA public page', kalyan_public: 'Kalyan public page',
    metals_dev_ibja: 'Metals.Dev IBJA authority', metals_dev_mcx: 'Metals.Dev MCX authority',
  }
  const status = provider?.status || 'not_polled'
  const tone = status === 'ok' || status === 'cached' ? 'healthy' : status === 'stale' ? 'stale' : status === 'error' ? 'error' : 'disabled'
  return <div className={`provider-health-card ${tone}`}>
    <div className="provider-health-top"><strong>{labels[id] || id.replaceAll('_', ' ')}</strong><span>{String(status).replaceAll('_', ' ').toUpperCase()}</span></div>
    <div className="provider-health-stats"><small>Requests: {provider?.request_count ?? 0}</small><small>Cache: {provider?.cache_ttl_seconds ?? '—'}s</small>{provider?.rate_limit_remaining != null && <small>Quota left: {provider.rate_limit_remaining}</small>}</div>
    {provider?.last_success_at && <small className="provider-health-time">Last success {fmtTime(provider.last_success_at)}</small>}
    {provider?.last_error && <small className="provider-health-error">{provider.last_error}</small>}
    {!provider?.enabled && <small className="provider-health-time">Not configured / disabled</small>}
  </div>
}

function SourceMeta({ point }) {
  if (!point) return <span className="source-meta">Source not connected</span>
  return <div className="source-meta"><span>{point.source || 'Unknown source'}</span><span>·</span><span>{fmtTime(point.timestamp)}</span><StatusPill status={point.status} /></div>
}

function KpiCard({ label, value, sub, icon: Icon, accent = '', change, point: sourcePoint }) {
  const positive = change != null && Number(change) >= 0
  return (
    <article className={`kpi-card ${accent}`}>
      <div className="kpi-head"><span>{label}</span><span className="kpi-icon"><Icon size={17} /></span></div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-foot">
        <span className="kpi-sub">{sub}</span>
        {change != null && <span className={`change ${positive ? 'positive' : 'negative'}`}>{positive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{pct(change)}</span>}
      </div>
      {sourcePoint && <SourceMeta point={sourcePoint} />}
    </article>
  )
}

function SectionTitle({ eyebrow, title, right }) {
  return <div className="section-title"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2></div>{right}</div>
}

function MetricRow({ label, value, note, tone = '' }) {
  return <div className="metric-row"><div><span>{label}</span>{note && <small>{note}</small>}</div><strong className={tone}>{value}</strong></div>
}

function AlertItem({ alert }) {
  return <div className={`alert-item ${alert.level || 'neutral'}`}>
    <span className="alert-icon">{alert.level === 'good' ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}</span>
    <div><strong>{alert.title}</strong><p>{alert.detail}</p></div>
  </div>
}

function SettingsPanel({ open, onClose, settings, onSaved }) {
  const [draft, setDraft] = useState(settings || {})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => setDraft(settings || {}), [settings])
  if (!open) return null

  const fields = [
    ['import_duty_pct', 'Effective gold import duty (%)', 'Used only in the simplified import-parity model. Current statutory setting should be verified when duties change.'],
    ['domestic_premium_pct', 'Domestic premium / friction (%)', 'Your estimate for local premium, freight and hedge friction, not an official fixed rate.'],
    ['local_cost_inr_per_10g', 'Other local cost (₹ / 10g)', 'Optional flat addition to the model.'],
    ['gst_pct', 'GST (%)', 'Applied to the estimated coin invoice.'],
    ['coin_premium_pct', 'Coin premium (%)', 'Enter Kalyan coin premium / minting premium from the quote.'],
    ['coin_fixed_fee_inr', 'Coin fixed fee (₹)', 'Packaging or other fixed coin charges, if any.'],
    ['coin_weight_g', 'Coin weight (grams)', 'Used in the purchase calculator.'],
    ['kalyan_max_premium_pct', 'Kalyan premium tolerance (%)', 'Dashboard flags a quote above this premium over IBJA 999.'],
    ['watch_discount_pct', 'Model discount watch threshold (%)', 'Used for model-spread monitoring only; not a guaranteed buy signal.'],
    ['alert_move_pct', 'Large move alert (%)', 'Flags a movement in retained XAU/INR snapshots.'],
  ]
  async function save() {
    setSaving(true); setError('')
    try {
      const payload = Object.fromEntries(fields.map(([key]) => [key, Number(draft[key])]).filter(([, value]) => Number.isFinite(value)))
      const result = await api('/api/settings', { method: 'POST', body: JSON.stringify(payload) })
      onSaved(result.settings)
      onClose()
    } catch (e) { setError(e.message) } finally { setSaving(false) }
  }
  return <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
    <aside className="settings-panel">
      <div className="panel-head"><div><div className="eyebrow">PERSONALISE YOUR MODEL</div><h2>Dashboard settings</h2></div><button className="icon-button" onClick={onClose}><X size={19} /></button></div>
      <div className="panel-info"><ShieldCheck size={16} /><span>Changes only affect estimates, alerts and comparisons. Source market prices are not modified.</span></div>
      <div className="settings-fields">
        {fields.map(([key, label, note]) => <label className="setting-field" key={key}>
          <span>{label}</span><input type="number" step="any" value={draft[key] ?? ''} onChange={(e) => setDraft((old) => ({ ...old, [key]: e.target.value }))} />
          <small>{note}</small>
        </label>)}
      </div>
      {error && <div className="error-text">{error}</div>}
      <div className="panel-actions"><button className="btn btn-ghost" onClick={onClose}>Cancel</button><button className="btn btn-gold" disabled={saving} onClick={save}>{saving ? 'Saving…' : 'Save assumptions'}</button></div>
    </aside>
  </div>
}

function ManualQuotePanel({ onApplied }) {
  const [field, setField] = useState('kalyan_24k_10g')
  const [value, setValue] = useState('')
  const [source, setSource] = useState('Kalyan Pune showroom')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('')
    try {
      await api('/api/overrides', { method: 'POST', body: JSON.stringify({ field, value: Number(value), source_label: source }) })
      setValue(''); await onApplied()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <form className="manual-form" onSubmit={submit}>
    <div className="manual-form-title"><div><div className="eyebrow">BRANCH QUOTE OVERRIDE</div><h3>Enter a verified rate</h3></div><span className="manual-tag">Manual source</span></div>
    <div className="manual-grid">
      <label><span>Rate type</span><select value={field} onChange={(e) => setField(e.target.value)}>
        <option value="kalyan_24k_10g">Kalyan 24K / 10g</option><option value="kalyan_22k_10g">Kalyan 22K / 10g</option><option value="ibja_999_10g">IBJA 999 / 10g</option><option value="mcx_999_10g">MCX reference / 10g</option><option value="usd_inr">USD/INR</option><option value="xau_usd_oz">XAU/USD / oz</option>
      </select></label>
      <label><span>Rate value</span><input type="number" min="0.0001" step="any" required value={value} onChange={(e) => setValue(e.target.value)} placeholder="Enter observed value" /></label>
      <label><span>Source / branch</span><input value={source} onChange={(e) => setSource(e.target.value)} required /></label>
      <button className="btn btn-gold" type="submit" disabled={busy || !value}>{busy ? 'Applying…' : 'Apply quote'}</button>
    </div>
    {error && <div className="error-text">{error}</div>}
    <p className="form-note">Manual rates override the corresponding automatic source until cleared. Confirm unit and purity before entering.</p>
  </form>
}

function CoinCalculator({ snapshot, settings }) {
  const [weight, setWeight] = useState(settings?.coin_weight_g ?? 10)
  const [premium, setPremium] = useState(settings?.coin_premium_pct ?? 0.75)
  const [fee, setFee] = useState(settings?.coin_fixed_fee_inr ?? 0)
  const [gst, setGst] = useState(settings?.gst_pct ?? 3)
  useEffect(() => { setWeight(settings?.coin_weight_g ?? 10); setPremium(settings?.coin_premium_pct ?? 0.75); setFee(settings?.coin_fixed_fee_inr ?? 0); setGst(settings?.gst_pct ?? 3) }, [settings])
  const base = snapshot?.calculations?.kalyan_24k_10g ?? snapshot?.calculations?.ibja_999_10g ?? snapshot?.calculations?.expected_landed_999_10g
  const cost = useMemo(() => {
    if (base == null) return null
    const metal = base * Number(weight || 0) / 10
    const addPremium = metal * Number(premium || 0) / 100
    const taxable = metal + addPremium + Number(fee || 0)
    const tax = taxable * Number(gst || 0) / 100
    return { metal, addPremium, taxable, tax, total: taxable + tax }
  }, [base, weight, premium, fee, gst])
  return <div className="coin-card">
    <div className="coin-card-top"><div><div className="eyebrow">PHYSICAL COIN ESTIMATOR</div><h3>What should I pay?</h3></div><div className="coin-mark"><Coins size={19} /></div></div>
    <div className="calc-inputs">
      <label><span>Weight (g)</span><input type="number" min="0.1" step="0.1" value={weight} onChange={(e) => setWeight(e.target.value)} /></label>
      <label><span>Coin premium (%)</span><input type="number" min="0" step="0.05" value={premium} onChange={(e) => setPremium(e.target.value)} /></label>
      <label><span>Fixed fee (₹)</span><input type="number" min="0" step="1" value={fee} onChange={(e) => setFee(e.target.value)} /></label>
      <label><span>GST (%)</span><input type="number" min="0" step="0.1" value={gst} onChange={(e) => setGst(e.target.value)} /></label>
    </div>
    <div className="calc-breakdown">
      <MetricRow label="Metal value" value={inr(cost?.metal)} note={`Base: ${snapshot?.calculations?.coin_estimate_basis || 'current reference'}`} />
      <MetricRow label="Coin premium" value={inr(cost?.addPremium)} />
      <MetricRow label="Fixed fees" value={inr(Number(fee || 0))} />
      <MetricRow label={`GST (${num(gst, 2)}%)`} value={inr(cost?.tax)} />
    </div>
    <div className="total-band"><div><span>Estimated invoice total</span><small>Estimate only — dealer quote prevails</small></div><strong>{inr(cost?.total)}</strong></div>
  </div>
}

function App() {
  const [snapshot, setSnapshot] = useState(null)
  const [history, setHistory] = useState([])
  const [settings, setSettings] = useState(null)
  const [overrides, setOverrides] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [showManual, setShowManual] = useState(false)
  const [historyRange, setHistoryRange] = useState(24)

  const load = useCallback(async (manual = false) => {
    if (manual) setBusy(true)
    setError('')
    try {
      const [data, hist, settingData] = await Promise.all([
        manual ? api('/api/refresh', { method: 'POST' }) : api('/api/dashboard'),
        api(`/api/history?hours=${historyRange}`),
        api('/api/settings'),
      ])
      setSnapshot(data); setHistory(hist.items || []); setSettings(settingData.settings); setOverrides(settingData.overrides || {}); setUpdated(new Date())
    } catch (e) { setError(e.message) } finally { if (manual) setBusy(false) }
  }, [historyRange])

  useEffect(() => { load(false) }, [load])
  useEffect(() => {
    const timer = window.setInterval(() => load(false), 60_000)
    return () => window.clearInterval(timer)
  }, [load])

  const c = snapshot?.calculations || {}
  const s = snapshot?.sources || {}
  const chartData = useMemo(() => history.map((item) => ({
    time: new Date(item.captured_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
    raw: item.calculations?.xau_inr_raw_10g ?? null,
    ibja: item.calculations?.ibja_999_10g ?? null,
    kalyan: item.calculations?.kalyan_24k_10g ?? null,
  })).filter((x) => x.raw != null || x.ibja != null || x.kalyan != null), [history])

  const onManualApplied = async () => { setShowManual(false); await load(true) }
  const onSettingsSaved = (data) => { setSettings(data); load(true) }

  async function clearOverride(field) {
    try { await api(`/api/overrides/${field}`, { method: 'DELETE' }); await load(true) }
    catch (e) { setError(e.message) }
  }

  const kalyanSpread = c.kalyan_vs_ibja_pct
  const rec = snapshot?.recommendation || { signal: 'LOADING', level: 'neutral', summary: 'Connecting to your configured market data sources.', reasons: [] }
  const signalIcon = rec.level === 'good' ? <CheckCircle2 size={20} /> : rec.level === 'warning' ? <AlertTriangle size={20} /> : <Gauge size={20} />
  const statusLine = snapshot?.market?.mcx_session || 'Checking market session…'

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-emblem"><span>Au</span></div><div><strong>AURUM<span> / INTELLIGENCE</span></strong><small>INDIA GOLD MARKET MONITOR</small></div></div>
      <div className="topbar-right"><div className="market-chip"><span className="live-dot" />{statusLine}</div><div className="updated-label"><Clock3 size={14} /> Updated {updated ? updated.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '—'}</div><button className="icon-button refresh-btn" title="Refresh feeds" onClick={() => load(true)} disabled={busy}>{busy ? <RefreshCw className="spin" size={17} /> : <RefreshCw size={17} />}</button><button className="icon-button" title="Settings" onClick={() => setSettingsOpen(true)}><Settings2 size={18} /></button></div>
    </header>

    <main className="main-wrap">
      <section className="hero-row">
        <div><div className="eyebrow"><span className="gold-line" /> MONITOR · BENCHMARK · DECIDE</div><h1>India Gold <em>Intelligence</em></h1><p className="hero-copy">A live pricing bridge from global spot markets to Indian benchmarks and your jeweller's quote.</p></div>
        <div className="hero-actions"><button className="btn btn-ghost" onClick={() => setShowManual((v) => !v)}><SlidersHorizontal size={15} /> Add branch quote</button><button className="btn btn-gold" onClick={() => load(true)} disabled={busy}><RefreshCw size={15} className={busy ? 'spin' : ''} /> Refresh now</button></div>
      </section>

      {error && <div className="error-banner"><AlertTriangle size={17} /><span>{error}</span><button onClick={() => setError('')}><X size={15} /></button></div>}

      <section className="kpi-grid">
        <KpiCard label="GOLD SPOT · XAU/USD" value={usd(s.xau_usd?.value)} sub="USD per troy ounce" icon={Globe2} accent="accent-amber" point={s.xau_usd} change={s.spot_change_pct} />
        <KpiCard label="USD / INR" value={s.usd_inr?.value == null ? '—' : `₹${num(s.usd_inr.value, 4)}`} sub="Rupees per US dollar" icon={Activity} point={s.usd_inr} />
        <KpiCard label="GLOBAL SPOT → INR" value={inr(c.xau_inr_raw_10g)} sub="Unadjusted 999 equivalent · 10g" icon={Zap} accent="accent-blue" />
        <KpiCard label="IBJA GOLD 999" value={inr(c.ibja_999_10g)} sub="Published reference · 10g" icon={Landmark} accent="accent-green" point={s.ibja_999_10g} />
        <KpiCard label="KALYAN 24K" value={inr(c.kalyan_24k_10g)} sub="Published rate · 10g" icon={Coins} point={s.kalyan_24k_10g} change={null} />
        <KpiCard label="MCX AUTHORITY FEED" value={inr(c.mcx_999_10g)} sub="Provider reference · 10g" icon={BarChart3} point={s.mcx_999_10g} />
      </section>

      <section className="analysis-grid">
        <article className="panel chart-panel">
          <div className="panel-heading"><div><div className="eyebrow">PRICE DISCOVERY</div><h2>Global-to-India price bridge</h2><p>Retained observations from this dashboard. No synthetic historical candles.</p></div><select className="range-select" value={historyRange} onChange={(e) => setHistoryRange(Number(e.target.value))}><option value="24">Last 24 hours</option><option value="72">Last 3 days</option><option value="168">Last 7 days</option><option value="720">Last 30 days</option></select></div>
          <div className="chart-legend"><span><i className="dot raw" />Global spot INR equivalent</span><span><i className="dot ibja" />IBJA 999</span><span><i className="dot kalyan" />Kalyan 24K</span></div>
          <div className="chart-wrap">
            {chartData.length < 2 ? <div className="chart-empty"><BarChart3 size={25} /><strong>Building your price history</strong><span>Historical lines will appear as the tracker collects observations. Connect providers and keep the backend running.</span></div> : <ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 12, right: 14, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 5" stroke="#263241" vertical={false} />
              <XAxis dataKey="time" tick={{ fill: '#8290a3', fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={30} />
              <YAxis tickFormatter={(v) => `₹${(v / 1000).toFixed(1)}k`} tick={{ fill: '#8290a3', fontSize: 11 }} tickLine={false} axisLine={false} width={52} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: '#121b27', border: '1px solid #2a3748', borderRadius: 10, color: '#eff4fa' }} formatter={(value) => inr(value)} labelStyle={{ color: '#9aa7b9' }} />
              <Line type="monotone" dataKey="raw" name="Global spot INR equivalent" stroke="#e0ad54" strokeWidth={2} dot={false} connectNulls />
              <Line type="monotone" dataKey="ibja" name="IBJA 999" stroke="#53c8a0" strokeWidth={2} dot={false} connectNulls />
              <Line type="monotone" dataKey="kalyan" name="Kalyan 24K" stroke="#82aefb" strokeWidth={2} dot={false} connectNulls />
            </LineChart></ResponsiveContainer>}
          </div>
          <div className="chart-foot"><span><Database size={13} /> Stored locally in SQLite</span><span>Polling: 60 seconds (backend setting)</span></div>
        </article>

        <article className={`panel recommendation-panel ${rec.level || 'neutral'}`}>
          <div className="rec-top"><div><div className="eyebrow">RULE-BASED DECISION SUPPORT</div><h2>Today's buying signal</h2></div><div className={`rec-icon ${rec.level || 'neutral'}`}>{signalIcon}</div></div>
          <div className={`signal-banner ${rec.level || 'neutral'}`}><span className="signal-pulse" />{rec.signal}</div>
          <p className="rec-summary">{rec.summary}</p>
          <div className="score-row"><span>Quote quality score</span><strong>{rec.score == null ? '—' : `${rec.score}/100`}</strong></div>
          <div className="score-track"><span style={{ width: `${Math.max(0, Math.min(100, rec.score || 0))}%` }} /></div>
          <div className="rec-reasons">{(rec.reasons || []).map((reason, i) => <div key={i}><CheckCircle2 size={14} /><span>{reason}</span></div>)}</div>
          <div className="rec-disclaimer">This is a transparent threshold rule, not a price forecast or guaranteed arbitrage signal.</div>
        </article>
      </section>

      <section className="detail-grid">
        <article className="panel benchmark-panel">
          <SectionTitle eyebrow="BENCHMARK RELATIVE VALUE" title="Where is India trading?" right={<span className="unit-tag">₹ / 10 grams</span>} />
          <div className="benchmark-table">
            <div className="table-head"><span>Reference</span><span>Price</span><span>vs IBJA 999</span></div>
            <div className="benchmark-row"><div className="benchmark-name"><span className="table-bullet global" /><div><strong>Global spot (unadjusted)</strong><small>XAU/USD × USD/INR</small></div></div><strong>{inr(c.xau_inr_raw_10g)}</strong><span className="muted">Pre-duty / pre-local premium</span></div>
            <div className="benchmark-row"><div className="benchmark-name"><span className="table-bullet model" /><div><strong>Modelled import parity</strong><small>Duty + domestic premium assumptions</small></div></div><strong>{inr(c.expected_landed_999_10g)}</strong><span className={`spread ${c.ibja_vs_model_pct <= 0 ? 'good' : 'warn'}`}>{pct(c.ibja_vs_model_pct)}</span></div>
            <div className="benchmark-row"><div className="benchmark-name"><span className="table-bullet ibja" /><div><strong>IBJA 999</strong><small>Official benchmark / public-page fallback</small></div></div><strong>{inr(c.ibja_999_10g)}</strong><span className="table-current">REFERENCE</span></div>
            <div className="benchmark-row"><div className="benchmark-name"><span className="table-bullet mcx" /><div><strong>MCX authority</strong><small>Feed availability depends on provider plan</small></div></div><strong>{inr(c.mcx_999_10g)}</strong><span className={`spread ${c.mcx_vs_ibja_pct <= 0 ? 'good' : 'warn'}`}>{pct(c.mcx_vs_ibja_pct)}</span></div>
            <div className="benchmark-row"><div className="benchmark-name"><span className="table-bullet kalyan" /><div><strong>Kalyan 24K</strong><small>Published rate; billing quote prevails</small></div></div><strong>{inr(c.kalyan_24k_10g)}</strong><span className={`spread ${kalyanSpread <= (settings?.kalyan_max_premium_pct ?? 0.75) ? 'good' : 'warn'}`}>{pct(kalyanSpread)}</span></div>
          </div>
          <div className="table-footnote">Spread = observed price relative to IBJA. The model is intentionally adjustable and is not a substitute for an importer's landed-cost calculation.</div>
        </article>

        <CoinCalculator snapshot={snapshot} settings={settings} />
      </section>

      <section className="detail-grid second-row">
        <article className="panel monitor-panel">
          <SectionTitle eyebrow="DAILY MONITORING" title="KPIs to watch" />
          <div className="monitor-grid">
            <div className="monitor-tile"><span>IBJA vs model parity</span><strong className={c.ibja_vs_model_pct <= 0 ? 'green-text' : 'amber-text'}>{pct(c.ibja_vs_model_pct)}</strong><small>Wholesale reference vs estimate</small></div>
            <div className="monitor-tile"><span>XAU/INR provider spread</span><strong className={c.xau_inr_cross_source_spread_pct != null && c.xau_inr_cross_source_spread_pct > 0.75 ? 'amber-text' : 'green-text'}>{pct(c.xau_inr_cross_source_spread_pct)}</strong><small>Cross-provider discrepancy; needs 2+ source checks</small></div>
            <div className="monitor-tile"><span>Kalyan premium vs IBJA</span><strong className={kalyanSpread <= (settings?.kalyan_max_premium_pct ?? 0.75) ? 'green-text' : 'amber-text'}>{pct(kalyanSpread)}</strong><small>Retail base-rate difference</small></div>
            <div className="monitor-tile"><span>MCX basis vs IBJA</span><strong>{pct(c.mcx_vs_ibja_pct)}</strong><small>Futures / authority spread</small></div>
            <div className="monitor-tile"><span>Expected 22K parity</span><strong>{inr(c.expected_916_10g)}</strong><small>91.6% of modelled 999 value</small></div>
            <div className="monitor-tile"><span>Expected 24K per gram</span><strong>{inr(c.expected_landed_999_per_g, 2)}</strong><small>Before GST and retail charges</small></div>
            <div className="monitor-tile"><span>XAU/INR 1-hour move</span><strong>{pct(c.xau_inr_1h_change_pct)}</strong><small>Requires a full hour of stored history</small></div>
            <div className="monitor-tile"><span>XAU/INR 24-hour move</span><strong>{pct(c.xau_inr_24h_change_pct)}</strong><small>Requires a full 24 hours of stored history</small></div>
            <div className="monitor-tile"><span>USD/INR 24-hour move</span><strong>{pct(c.usd_inr_24h_change_pct)}</strong><small>FX contribution to Indian gold price</small></div>
            <div className="monitor-tile"><span>IBJA 24-hour move</span><strong>{pct(c.ibja_24h_change_pct)}</strong><small>Locally captured benchmark history</small></div>
          </div>
        </article>

        <article className="panel alerts-panel">
          <SectionTitle eyebrow="AUTOMATED WATCHLIST" title="Alerts & suggestions" right={<span className="alert-count">{snapshot?.alerts?.length || 0} ACTIVE</span>} />
          <div className="alerts-list">
            {(snapshot?.alerts || []).length ? snapshot.alerts.map((alert, i) => <AlertItem key={`${alert.title}-${i}`} alert={alert} />) : <div className="no-alert"><CheckCircle2 size={20} /><span>No threshold alerts. Keep checking live source freshness.</span></div>}
          </div>
        </article>
      </section>

      {showManual && <section className="panel manual-panel"><ManualQuotePanel onApplied={onManualApplied} /></section>}
      {Object.keys(overrides).length > 0 && <section className="panel overrides-panel"><div className="override-heading"><div><div className="eyebrow">USER-ENTERED INPUTS</div><h3>Active manual overrides</h3></div><span className="manual-tag">Manual values take precedence</span></div><div className="override-list">{Object.entries(overrides).map(([field, item]) => <div className="override-chip" key={field}><div><strong>{field.replaceAll('_', ' ')}</strong><small>{item.source} · {fmtTime(item.timestamp)}</small></div><button onClick={() => clearOverride(field)}>Clear</button></div>)}</div></section>}

      <RetailerBoard />

      <section className="panel source-panel">
        <div className="source-header"><div><div className="eyebrow">DATA PROVENANCE</div><h2>Live feeds & reliability</h2><p>Every signal should be traceable to its source and timestamp.</p></div><div className="source-header-right"><span className="source-legend"><i className="live-key" /> Provider feed</span><span className="source-legend"><i className="delayed-key" /> Public-page / daily fallback</span></div></div>
        <div className="source-grid">
          {[
            ['XAU/USD spot', s.xau_usd, 'Primary: XAUS; fallback: Gold-API.com, GoldAPI.dev / optional Metals.Dev'],
            ['USD/INR', s.usd_inr, 'Primary: XAUS; fallback: GoldAPI.dev, Twelve Data or Frankfurter daily FX'],
            ['XAUS XAU/INR', s.xau_inr_xaus_10g, 'Raw INR spot cross-check from XAUS'],
            ['Gold-API.com XAU/INR', s.xau_inr_gold_api_com_10g, 'Keyless live INR spot cross-check'],
            ['GoldAPI.dev XAU/INR', s.xau_inr_goldapi_dev_10g, 'Optional live cross-check; API key required'],
            ['GoldPrice.dev XAU/INR', s.xau_inr_goldprice_dev_10g, 'Free cross-check; 15-minute delayed'],
            ['IBJA 999', s.ibja_999_10g, 'Public IBJA page scrape or optional authority feed'],
            ['MCX gold', s.mcx_999_10g, 'Licensed / eligible MCX authority feed only'],
            ['Kalyan 24K', s.kalyan_24k_10g, 'Kalyan public rate page; may not be Pune branch-specific'],
          ].map(([label, pointData, description]) => <div className="source-card" key={label}>
            <div className="source-card-top"><strong>{label}</strong><StatusPill status={pointData?.status} /></div>
            <span className="source-card-value">{pointData?.value == null ? 'No quote' : label === 'XAU/USD spot' ? usd(pointData.value) : inr(pointData.value)}</span>
            <small>{pointData?.source || description}</small>
            <small className="source-time">{pointData?.note || description} · {fmtTime(pointData?.timestamp)}</small>
          </div>)}
        </div>
        <div className="source-links"><a href="https://xaus.com/api/" target="_blank" rel="noreferrer">XAUS API <ExternalLink size={12} /></a><a href="https://gold-api.com/docs" target="_blank" rel="noreferrer">Gold-API.com <ExternalLink size={12} /></a><a href="https://goldapi.dev/docs" target="_blank" rel="noreferrer">GoldAPI.dev docs <ExternalLink size={12} /></a><a href="https://goldprice.dev/docs/api-reference" target="_blank" rel="noreferrer">GoldPrice.dev docs <ExternalLink size={12} /></a><a href="https://frankfurter.dev/" target="_blank" rel="noreferrer">Frankfurter FX <ExternalLink size={12} /></a><a href="https://ibjarates.com/" target="_blank" rel="noreferrer">IBJA published rates <ExternalLink size={12} /></a><a href="https://www.mcxindia.com/" target="_blank" rel="noreferrer">MCX <ExternalLink size={12} /></a></div>
        <div className="provider-health-section"><div className="eyebrow">PROVIDER HEALTH · CACHE & QUOTA CONTROL</div><div className="provider-health-grid">{Object.entries(snapshot?.provider_health || {}).map(([id, provider]) => <ProviderHealthCard key={id} id={id} provider={provider} />)}</div></div>
      </section>

      <footer className="footer"><div className="footer-brand"><span className="brand-emblem mini"><span>Au</span></span><span>GOLD INTELLIGENCE</span></div><p>For research and purchase comparison only. Not investment advice. Market data may be delayed, incomplete or subject to vendor terms. Confirm the final price, purity, HUID, GST and buyback policy with the seller.</p><span className="footer-date">{snapshot?.market?.india_time ? `IST · ${fmtTime(snapshot.market.india_time)}` : 'Asia/Kolkata'}</span></footer>
    </main>
    <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} settings={settings} onSaved={onSettingsSaved} />
  </div>
}

export default App
