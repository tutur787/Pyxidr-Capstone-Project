import { useState, useRef, useEffect } from 'react'
import type { ChatMessage } from '../../types'

const WELCOME: ChatMessage = {
  role: 'assistant',
  content: "Hello! I'm your FABN Portfolio AI. Ask me about what's on screen right now — \"what are the recommended trades?\", \"what's driving RBC?\" — or ask me to run the optimizer with different parameters (e.g. \"run the optimization for 2025-01-15 with 20% cost of capital, confirm\").",
  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
}

function nowTs() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function AIChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [hfConfigured, setHfConfigured] = useState<boolean | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    fetch('/api/agent/status')
      .then(res => res.json())
      .then(data => setHfConfigured(!!data.hf_token_configured))
      .catch(() => setHfConfigured(false))
  }, [])

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    setMessages(prev => [...prev, { role: 'user', content: text, timestamp: nowTs() }])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      const payload = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: formatReply(payload), timestamp: nowTs() }])
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: "Couldn't reach the backend — is it running?",
        timestamp: nowTs(),
      }])
    } finally {
      setLoading(false)
    }
  }

  function formatReply(payload: { ok: boolean; message: string; data?: Record<string, unknown> }): string {
    const parts = [payload.message]
    const data = payload.data
    if (data?.query_id === 'recommended_trades' && Array.isArray(data.rows)) {
      const rows = data.rows as Array<{ action: string; cusip: string; delta_usd: number; sap_score_bps: number }>
      if (rows.length) {
        parts.push(rows.slice(0, 8).map(r =>
          `${r.action} ${r.cusip} — $${Math.abs(r.delta_usd).toLocaleString()} (${r.sap_score_bps} bps SAP)`
        ).join('\n'))
      }
    } else if (data?.query_id === 'top_holdings_delta' && Array.isArray(data.rows)) {
      const rows = data.rows as Array<{ bond: string; delta_usd: number }>
      if (rows.length) {
        parts.push(rows.slice(0, 8).map(r => `${r.bond}: Δ$${r.delta_usd.toLocaleString()}`).join('\n'))
      }
    } else if (data?.query_id === 'summary_metrics') {
      const d = data as Record<string, number | string>
      parts.push(
        `SAP objective: $${Number(d.sap_objective_usd).toLocaleString()} | ` +
        `Duration: ${d.duration_avg_years}y | Bonds: ${d.n_bonds_selected}`
      )
    } else if (data?.query_id === 'contribution_analysis') {
      if (typeof data.narrative === 'string' && data.narrative) parts.push(data.narrative)
      if (data.reconciliation_warning) parts.push(String(data.reconciliation_warning))
    }
    return parts.filter(Boolean).join('\n\n')
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="bg-surface-1 rounded-2xl border border-border p-4 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-7 h-7 rounded-full bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400 text-sm">
          ◈
        </div>
        <div>
          <h2 className="text-text-primary font-semibold text-sm">AI Portfolio Assistant</h2>
          <p className="text-text-muted text-xs">Ask questions about your portfolio</p>
        </div>
        <span className={`ml-auto text-xs px-2 py-0.5 rounded-full border ${
          hfConfigured === null
            ? 'text-text-muted border-border'
            : hfConfigured
              ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
              : 'text-amber-400 border-amber-500/30 bg-amber-500/10'
        }`}>
          {hfConfigured === null ? 'Checking…' : hfConfigured ? 'Live' : 'HF_TOKEN not set'}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 mb-3 pr-1 min-h-0">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-xs leading-relaxed
              ${msg.role === 'user'
                ? 'bg-amber-500/15 border border-amber-500/20 text-amber-100'
                : 'bg-surface-2 border border-border text-text-secondary'
              }`}>
              <p>{msg.content}</p>
              <p className="text-text-muted text-[10px] mt-1 text-right">{msg.timestamp}</p>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-surface-2 border border-border rounded-2xl px-3 py-2">
              <span className="text-text-muted text-xs animate-pulse">Thinking…</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about your portfolio…"
          className="flex-1 bg-surface-2 border border-border rounded-2xl px-3 py-2 text-sm text-text-primary
            placeholder-text-muted focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-all"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || loading}
          className="px-4 py-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-30 disabled:cursor-not-allowed
            text-gray-900 font-semibold text-sm rounded-2xl transition-colors flex-shrink-0"
        >
          ↑
        </button>
      </div>
    </div>
  )
}
