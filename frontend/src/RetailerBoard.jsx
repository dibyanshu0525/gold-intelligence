import { useCallback, useEffect, useMemo, useState } from 'react'
import { ExternalLink, Plus, RefreshCw, Save, Trash2, Store, Coins } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || ''
const money = (value, digits = 0) => value == null || !Number.isFinite(Number(value))
  ? '—'
  : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(Number(value))
const time = (value) => {
  if (!value) return 'No quote entered'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? 'Timestamp unavailable' : d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`)
  return body
}

export default function RetailerBoard() {
  const [directory, setDirectory] = useState(null)
  const [city, setCity] = useState('Pune')
  const [filter, setFilter] = useState('All')
  const [selected, setSelected] = useState('kalyan')
  const [rate22, setRate22] = useState('')
  const [rate24, setRate24] = useState('')
  const [coin10, setCoin10] = useState('')
  const [making, setMaking] = useState('')
  const [source, setSource] = useState('Official website / showroom quotation')
  const [sourceUrl, setSourceUrl] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [formOpen, setFormOpen] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await request(`/api/retailers?city=${encodeURIComponent(city)}`)
      setDirectory(data)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [city])

  useEffect(() => { load() }, [load])

  const rows = directory?.retailers || []
  const visible = useMemo(() => rows.filter((r) => {
    if (filter === 'All') return true
    if (filter === 'Jewellery') return !['Bullion / minted coins', 'Digital gold / delivery'].includes(r.segment)
    if (filter === 'Coins & bullion') return ['Bullion / minted coins', 'Digital gold / delivery'].includes(r.segment)
    if (filter === 'Pune / Maharashtra') return /Pune|Maharashtra/.test(r.coverage)
    return true
  }), [rows, filter])

  const resetForm = () => {
    setRate22(''); setRate24(''); setCoin10(''); setMaking('')
    setSource('Official website / showroom quotation'); setSourceUrl(''); setNotes('')
  }

  const chooseRetailer = (id) => {
    setSelected(id)
    const row = rows.find((r) => r.id === id)
    if (row) setSourceUrl(row.rate_url || row.website)
    const q = row?.quote
    if (q?.status === 'manual') {
      setRate22(q.gold_22k_per_g ?? '')
      setRate24(q.gold_24k_per_g ?? '')
      setCoin10(q.coin_10g_total ?? '')
      setMaking(q.making_charge_pct ?? '')
      setSource(q.source || 'Verified retailer page / showroom quote')
      setNotes(q.notes || '')
    } else {
      resetForm()
      setSourceUrl(row?.rate_url || row?.website || '')
    }
  }

  const save = async (event) => {
    event.preventDefault()
    setBusy(true); setError(''); setNotice('')
    const payload = {
      retailer_id: selected,
      city,
      gold_22k_per_g: rate22 === '' ? null : Number(rate22),
      gold_24k_per_g: rate24 === '' ? null : Number(rate24),
      coin_10g_total: coin10 === '' ? null : Number(coin10),
      making_charge_pct: making === '' ? null : Number(making),
      source_label: source,
      source_url: sourceUrl || null,
      notes: notes || null,
    }
    try {
      await request('/api/retailer-quotes', { method: 'POST', body: JSON.stringify(payload) })
      await load()
      setNotice(`Saved ${rows.find((r) => r.id === selected)?.name || selected} quote for ${city}.`)
      setFormOpen(false)
    } catch (err) {
      setError(err.message)
    } finally { setBusy(false) }
  }

  const remove = async (id) => {
    setBusy(true); setError(''); setNotice('')
    try {
      await request(`/api/retailer-quotes/${id}?city=${encodeURIComponent(city)}`, { method: 'DELETE' })
      await load()
      setNotice('Saved quote removed. Kalyan may still appear from its automatic rate feed.')
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const edit = (row) => {
    chooseRetailer(row.id)
    setFormOpen(true)
  }

  return <section className="panel retailer-panel">
    <div className="retailer-header">
      <div>
        <div className="eyebrow">INDIA RETAIL PRICE WATCH</div>
        <h2>Compare gold buying options</h2>
        <p>Major jewellers, regional retailers and physical bullion sellers. Compare only quotes with matching purity, city and timestamp.</p>
      </div>
      <div className="retailer-actions">
        <button className="btn btn-ghost" onClick={load} disabled={busy}><RefreshCw size={14} /> Refresh</button>
        <button className="btn btn-gold" onClick={() => { setFormOpen((v) => !v); setError(''); setNotice('') }}><Plus size={14} /> Add retailer quote</button>
      </div>
    </div>

    <div className="retailer-summary">
      <div><span>Retailers tracked</span><strong>{directory?.summary?.retailer_count ?? '—'}</strong></div>
      <div><span>Quotes recorded</span><strong>{directory?.summary?.quoted_count ?? '—'}</strong></div>
      <div><span>Lowest 24K base rate</span><strong>{directory?.summary?.gold_24k_lowest ? rows.find((r) => r.id === directory.summary.gold_24k_lowest)?.name : 'Awaiting quotes'}</strong></div>
      <div><span>Lowest 10g coin bill</span><strong>{directory?.summary?.coin_10g_lowest ? rows.find((r) => r.id === directory.summary.coin_10g_lowest)?.name : 'Awaiting quotes'}</strong></div>
    </div>

    {formOpen && <form className="retailer-quote-form" onSubmit={save}>
      <div className="retailer-form-title"><div><strong>Record a verified retailer quote</strong><small>Rates are per gram before GST; coin price is the quoted total for a 10g 24K coin.</small></div><span className="manual-tag">Manual / verified entry</span></div>
      <div className="retailer-form-grid">
        <label><span>Retailer</span><select value={selected} onChange={(e) => chooseRetailer(e.target.value)}>{rows.map((r) => <option value={r.id} key={r.id}>{r.name}</option>)}</select></label>
        <label><span>City / market</span><input value={city} onChange={(e) => setCity(e.target.value)} required /></label>
        <label><span>22K rate (₹ / g)</span><input type="number" min="1" step="0.01" value={rate22} onChange={(e) => setRate22(e.target.value)} placeholder="Optional" /></label>
        <label><span>24K rate (₹ / g)</span><input type="number" min="1" step="0.01" value={rate24} onChange={(e) => setRate24(e.target.value)} placeholder="Optional" /></label>
        <label><span>10g 24K coin final price (₹)</span><input type="number" min="1" step="0.01" value={coin10} onChange={(e) => setCoin10(e.target.value)} placeholder="Include taxes / premiums" /></label>
        <label><span>Making charge (%)</span><input type="number" min="0" max="100" step="0.01" value={making} onChange={(e) => setMaking(e.target.value)} placeholder="Optional" /></label>
        <label><span>Quote source</span><input value={source} onChange={(e) => setSource(e.target.value)} required /></label>
        <label><span>Source URL</span><input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="Official rate page / quote link" /></label>
      </div>
      <label className="retailer-notes"><span>Notes (GST basis, coin premium, store, validity, buyback)</span><input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Pune branch, 999 purity, GST included, quote valid till 6 PM" /></label>
      <div className="retailer-form-actions"><button className="btn btn-ghost" type="button" onClick={() => { resetForm(); setFormOpen(false) }}>Cancel</button><button className="btn btn-gold" type="submit" disabled={busy}><Save size={14} /> {busy ? 'Saving…' : 'Save quote'}</button></div>
    </form>}

    <div className="retailer-toolbar">
      <div className="retailer-filters">
        {['All', 'Jewellery', 'Coins & bullion', 'Pune / Maharashtra'].map((item) => <button key={item} className={filter === item ? 'active' : ''} onClick={() => setFilter(item)}>{item}</button>)}
      </div>
      <span className="retailer-city"><Store size={13} /> {city} market</span>
    </div>

    <div className="retailer-table-wrap">
      <table className="retailer-table">
        <thead><tr><th>Retailer / channel</th><th>22K / g</th><th>24K / g</th><th>10g coin total</th><th>Quote status</th><th>Links / action</th></tr></thead>
        <tbody>{visible.map((r) => <tr key={r.id}>
          <td><strong>{r.name}</strong><small>{r.segment} · {r.coverage}</small>{r.notes && <small className="retailer-notice">{r.notes}</small>}</td>
          <td>{money(r.gold_22k_per_g, 2)}</td>
          <td>{money(r.gold_24k_per_g, 2)}</td>
          <td>{money(r.coin_10g_total, 0)}</td>
          <td><span className={`quote-state ${r.quote_status === 'not_entered' ? 'missing' : r.quote_status === 'manual' ? 'manual' : 'feed'}`}>{r.quote_status === 'not_entered' ? 'QUOTE NEEDED' : r.quote_status === 'manual' ? 'MANUAL QUOTE' : r.quote_status === 'stale' ? 'STALE FEED' : 'PUBLISHED FEED'}</span><small>{time(r.quote_timestamp)}</small>{r.quote_source && <small>{r.quote_source}</small>}</td>
          <td><div className="retailer-row-actions"><a href={r.rate_url || r.website} target="_blank" rel="noreferrer" title="Open official rate page">Rate page <ExternalLink size={11} /></a><button onClick={() => edit(r)} title="Add or edit quote">{r.quote_status === 'manual' ? 'Edit' : 'Add quote'}</button>{r.quote_status === 'manual' && <button className="icon-action" onClick={() => remove(r.id)} title="Remove quote"><Trash2 size={12} /></button>}</div></td>
        </tr>)}</tbody>
      </table>
      {!visible.length && <div className="retailer-empty">No retailers match this filter.</div>}
    </div>

    {directory?.provider_health && <div className="retailer-feed-health">{Object.entries(directory.provider_health).map(([id, health]) => <span key={id} className={health.status === 'ok' || health.status === 'cached' ? 'healthy' : health.status === 'stale' ? 'stale' : 'error'}><strong>{id.replaceAll('_', ' ')}</strong> · {health.status.toUpperCase()}{health.last_error ? ` — ${health.last_error}` : ''}</span>)}</div>}
    {error && <div className="retailer-error">{error}</div>}
    {notice && <div className="retailer-notice-bar">{notice}</div>}
    <div className="retailer-disclaimer"><Coins size={14} /><span>Do not treat an empty row as ₹0 or a retailer as cheaper. Automatic published rates are attempted for Kalyan, Tanishq, Malabar and Senco when their official pages expose current values. Other retailers remain quote-needed until a dated official or showroom rate is entered; keep 22K/24K base rates separate from the final coin invoice. Digital gold has different fees, custody and redemption risks.</span></div>
  </section>
}
