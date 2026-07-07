import { useState, useRef, useEffect } from 'react'
import type { ChatMessage } from '../../types'

const STUB_REPLY = "I'm the FABN Portfolio AI assistant. Full integration is coming soon — I'll be able to answer questions about your portfolio composition, optimization constraints, risk exposure, and suggested trades. Stay tuned!"

const WELCOME: ChatMessage = {
  role: 'assistant',
  content: "Hello! I'm your FABN Portfolio AI. Ask me about your portfolio, risk metrics, or suggested trades. (Full AI integration coming soon.)",
  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
}

export default function AIChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    setMessages(prev => [...prev, { role: 'user', content: text, timestamp: ts }])
    setInput('')
    setLoading(true)

    setTimeout(() => {
      const replyTs = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      setMessages(prev => [...prev, { role: 'assistant', content: STUB_REPLY, timestamp: replyTs }])
      setLoading(false)
    }, 800)
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
        <span className="ml-auto text-xs text-text-muted border border-border px-2 py-0.5 rounded-full">
          Stub mode
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
