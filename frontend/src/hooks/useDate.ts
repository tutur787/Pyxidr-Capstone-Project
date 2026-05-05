import { useState, useCallback } from 'react'
import { DATE_MIN, DATE_MAX } from '../data/stubs'

function addDays(iso: string, delta: number): string {
  const d = new Date(iso)
  d.setDate(d.getDate() + delta)
  return d.toISOString().slice(0, 10)
}

function clamp(iso: string): string {
  if (iso < DATE_MIN) return DATE_MIN
  if (iso > DATE_MAX) return DATE_MAX
  return iso
}

export function useDate(initial = '2025-01-15') {
  const [date, setDate] = useState(clamp(initial))

  const advanceDate = useCallback((delta: number) => {
    setDate(prev => clamp(addDays(prev, delta)))
  }, [])

  const isAtMin = date <= DATE_MIN
  const isAtMax = date >= DATE_MAX

  const formatDisplay = (iso: string) => {
    const d = new Date(iso + 'T00:00:00')
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  }

  return { date, advanceDate, isAtMin, isAtMax, formatDisplay }
}
