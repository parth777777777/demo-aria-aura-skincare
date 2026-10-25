import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { AlertCircle, AudioLines, Check, CircleAlert, Clock, Copy, FileText, Leaf, LoaderCircle, Mic, PackageCheck, Phone, PhoneOff, RotateCcw, Sparkles, Truck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { ScrollArea } from '@/components/ui/scroll-area'
import { callReducer, initialCallState } from './state/callReducer.js'
import { selectVoiceState } from './state/selectors.js'
import { useMockReplay } from './hooks/useMockReplay.js'
import { useHashRoute } from './hooks/useHashRoute.js'
import { getCustomerIntentLabel, getOrderIdLabel, getResolutionPill, getVisibleNotice } from './lib/display.js'

const orders = [
  { id: 'ORD-101', product: 'Vitamin C Serum 30ml', status: 'Out for Delivery', detail: 'Today by 6 PM', hint: 'Where is my order?', Icon: Truck, tone: 'sage' },
  { id: 'ORD-102', product: 'Hydrating Sunscreen SPF 50', status: 'Delivered', detail: '14 days ago', hint: 'Can I return this?', Icon: PackageCheck, tone: 'success' },
  { id: 'ORD-103', product: 'Green Tea Face Wash + Toner', status: 'Processing', detail: 'Ordered 3 hours ago', hint: 'Cancel this order.', Icon: Clock, tone: 'warning' },
]
const labels = { idle: 'Ready when you are', connecting: 'Connecting', listening: 'Listening', thinking: 'Aria is thinking', speaking: 'Aria is speaking', ended: 'Call ended', error: 'Call error' }
const summaryKeys = ['customer_intent', 'order_id', 'resolution_status', 'call_summary']

function VoiceOrb({ state }) {
  const icons = { idle: <Leaf />, connecting: <LoaderCircle className="orb-spin" />, listening: <Mic />, thinking: <span aria-hidden="true">•••</span>, speaking: <AudioLines />, ended: <Check />, error: <CircleAlert /> }
  return <div className={`grid size-[62px] shrink-0 place-items-center rounded-full bg-muted text-primary orb-${state}`} aria-hidden="true"><div className={`grid size-12 place-items-center rounded-full border border-primary ${state === 'connecting' ? 'border-dotted border-2' : state === 'thinking' ? 'border-dashed border-2' : ['listening', 'speaking'].includes(state) ? 'border-2' : ''}`}>{icons[state]}</div></div>
}

function OrderResult({ tool }) {
  const result = tool.result
  if (tool.name !== 'get_order_details' || !result || result.ok === false) return null
  const order = result.order || result
  return <Card className="mt-3 w-full max-w-[340px] bg-card animate-in fade-in slide-in-from-bottom-2 duration-200 delay-150 motion-reduce:animate-none"><CardContent className="p-3"><div className="flex items-center justify-between gap-2"><span className="text-sm font-bold uppercase tracking-widest text-muted-foreground">Order details</span><span className="font-mono text-sm">{order.order_id || order.id || tool.args?.order_id}</span></div><div className="mt-2 grid grid-cols-[65px_1fr] gap-x-2.5 gap-y-2 border-t border-border pt-2.5 text-sm"><span className="text-muted-foreground">Status</span><strong className="font-medium">{order.status || '—'}</strong><span className="text-muted-foreground">Items</span><strong className="font-medium">{Array.isArray(order.items) ? order.items.map((item) => item.name || item).join(', ') : order.items || '—'}</strong></div></CardContent></Card>
}

function App() {
  const [state, dispatch] = useReducer(callReducer, initialCallState)
  const [elapsed, setElapsed] = useState(0)
  const [route, setRoute] = useHashRoute()
  const [mockData, setMockData] = useState(null)
  const [copied, setCopied] = useState(false)
  const copyTimer = useRef(null)
  const transcriptRef = useRef(null)
  const voiceState = selectVoiceState(state)
  const replayEvents = useMemo(() => mockData?.lookup || [], [mockData])
  const { startMockReplay, stopMockReplay } = useMockReplay(dispatch, replayEvents, 800)
  const [scenario, setScenario] = useState('')
  const scenarioEvents = useMemo(() => scenario && mockData ? mockData[scenario] : [], [scenario, mockData])
  const { startMockReplay: startScenarioReplay, stopMockReplay: stopScenarioReplay } = useMockReplay(dispatch, scenarioEvents, 800)
  const callActive = ['connecting', 'live', 'ending'].includes(state.status.state)
  const debug = new URLSearchParams(window.location.search).get('debug') === '1'

  useEffect(() => {
    if (import.meta.env.DEV) {
      import('./mocks/call-events.json').then((module) => setMockData(module.default))
    }
  }, [])
  useEffect(() => () => window.clearTimeout(copyTimer.current), [])
  useEffect(() => {
    if (state.status.state !== 'live') return undefined
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000)
    return () => clearInterval(timer)
  }, [state.status.state])
  useEffect(() => {
    if (scenario) startScenarioReplay()
  }, [scenario, startScenarioReplay])
  useEffect(() => {
    const viewport = transcriptRef.current?.querySelector('[data-slot="scroll-area-viewport"]')
    if (viewport && viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 120) viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })
  }, [state.turns, state.tools])

  const runReplay = () => {
    stopMockReplay()
    stopScenarioReplay()
    dispatch({ type: 'call_requested' })
    setElapsed(0)
    startMockReplay()
  }
  const runScenario = (key) => {
    setScenario(key)
    stopMockReplay()
    stopScenarioReplay()
    dispatch({ type: 'reset' })
    dispatch({ type: 'call_requested' })
    setElapsed(0)
  }
  const startAnother = () => {
    stopMockReplay()
    stopScenarioReplay()
    dispatch({ type: 'reset' })
    setElapsed(0)
    window.location.hash = '#/'
    setRoute('call')
  }
  const navigateSummary = () => { window.location.hash = '#/summary'; setRoute('summary') }
  const time = `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(elapsed % 60).padStart(2, '0')}`
  const summary = state.summary && Object.fromEntries(summaryKeys.map((key) => [key, state.summary[key]]))
  const { errorMessage, sessionLimit } = getVisibleNotice({ error: state.error, status: state.status, turnCount: state.turns.length })
  const copySummary = async () => {
    await navigator.clipboard.writeText(JSON.stringify(summary, null, 2))
    setCopied(true)
    window.clearTimeout(copyTimer.current)
    copyTimer.current = window.setTimeout(() => setCopied(false), 2000)
  }

  return <main className="mx-auto w-full max-w-[1440px] px-[13px] sm:px-[22px] lg:px-[42px]">
    <header className="flex h-[66px] items-center justify-between border-b border-border sm:h-[82px]"><a href="#/" onClick={() => setRoute('call')} className="flex items-center gap-3 font-sans text-sm font-bold tracking-[.16em] text-primary"><span className="grid size-[34px] place-items-center rounded-full bg-primary text-primary-foreground"><Sparkles size={17} /></span><span className="leading-[1.05]">AURA<small className="mt-[2px] block text-[13px] leading-[1.05] tracking-[.24em]">SKINCARE</small></span></a></header>
    {route === 'summary' ? <section className="mx-auto my-8 w-full max-w-3xl rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-8" aria-labelledby="summary-heading">
      {summary ? <><div className="flex flex-wrap items-center justify-between gap-3"><h1 id="summary-heading" className="font-heading text-3xl">Call summary</h1>{(() => { const item = getResolutionPill(summary.resolution_status); return <Badge className={`h-auto gap-2 rounded-full px-3 py-1 text-sm font-medium normal-case ${item.style}`}><item.Icon size={16} />{item.label}</Badge> })()}</div><dl className="mt-6 grid gap-4"><div><dt className="text-sm font-bold uppercase tracking-widest text-muted-foreground">Customer intent</dt><dd className="mt-1">{getCustomerIntentLabel(summary.customer_intent)}</dd></div><div><dt className="text-sm font-bold uppercase tracking-widest text-muted-foreground">Order ID</dt><dd className="mt-1 font-mono">{getOrderIdLabel(summary.order_id)}</dd></div><div><dt className="text-sm font-bold uppercase tracking-widest text-muted-foreground">Call summary</dt><dd className="mt-1 leading-relaxed">{summary.call_summary}</dd></div></dl><div className="mt-6 flex items-center justify-between gap-3"><h2 className="font-heading text-xl">Structured summary (JSON)</h2><Button variant="outline" size="sm" onClick={copySummary} aria-live="polite">{copied ? <Check /> : <Copy />}{copied ? 'Copied' : 'Copy'}</Button></div><Card className="mt-3 rounded-2xl bg-card"><CardContent className="p-5"><pre className="m-0 whitespace-pre-wrap break-words font-mono text-sm leading-relaxed">{JSON.stringify(summary, null, 2)}</pre></CardContent></Card><div className="mt-6 flex flex-wrap gap-3"><Button className="h-[52px] rounded-full text-base" onClick={startAnother}><RotateCcw />Start another call</Button><Button className="h-[52px] rounded-full text-base" variant="outline" onClick={() => { window.location.hash = '#/'; setRoute('call') }}>Back to conversation</Button></div></> : <><h1 id="summary-heading" className="font-heading text-3xl">No call to summarize</h1><Button className="mt-5 h-[52px] rounded-full text-base" onClick={() => { window.location.hash = '#/'; setRoute('call') }}>Back to call</Button></>}
    </section> : <div className="grid items-stretch gap-4 py-4 lg:grid-cols-[minmax(360px,.82fr)_minmax(0,1.18fr)] lg:gap-7 lg:py-[30px]">
      <section className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-sm lg:min-h-[730px]" aria-labelledby="call-title">
        <div className="relative h-[155px] overflow-hidden bg-gradient-to-br from-[#dce5d6] via-[#9daf99] to-[#758b76] sm:h-[190px] lg:h-[206px]"><img src="/src/assets/companion.webp" alt="" className="absolute size-full object-cover" onError={(event) => { event.currentTarget.style.display = 'none' }} /><span className="absolute bottom-[18px] left-6 font-heading text-lg italic text-[#263b2e]">A little care goes a long way</span></div>
        <div className="w-full p-5 sm:p-8 lg:px-[34px] lg:py-[27px]"><h1 id="call-title" className="my-3 font-heading text-[39px] font-medium leading-tight tracking-[-.045em] sm:text-5xl">Ask Aria about<br />your order.</h1><div className="my-4 flex items-center gap-3.5"><VoiceOrb state={voiceState} /><div className="flex flex-col gap-1"><strong className="text-base">{labels[voiceState]}</strong><span className="text-sm tabular-nums text-muted-foreground">{state.status.state === 'live' ? time : ' '}</span></div></div>
          {state.status.state === 'ended' ? <div className="grid gap-2">{state.status.reason === 'error' ? null : state.summary ? <Button className="h-[52px] w-full rounded-full text-base" onClick={navigateSummary}><FileText />View call summary</Button> : <p className="py-2 text-center text-sm text-muted-foreground">A summary isn't available for this call.</p>}<Button className="h-[52px] w-full rounded-full text-base" variant="outline" onClick={startAnother}><RotateCcw />Start another call</Button></div> : <Button className="h-[52px] w-full rounded-full text-base" variant={callActive ? 'destructive' : 'default'} onClick={callActive ? () => dispatch({ type: 'status', state: 'ended', reason: 'user_ended' }) : runReplay}>{callActive ? <><PhoneOff /> End call</> : <><Phone /> Start a call</>}</Button>}
          <p className="mt-3 text-center text-sm text-muted-foreground">You're talking to an AI care agent</p>
          {import.meta.env.DEV && <div className="mt-4 flex flex-col items-center gap-2"><Button size="sm" variant="outline" onClick={runReplay}>Run mock replay</Button><label className="flex items-center gap-2 text-sm text-muted-foreground">Scenario<select className="h-9 rounded-md border border-border bg-background px-2 text-foreground" value={scenario} onChange={(event) => runScenario(event.target.value)} aria-label="Run mock scenario"><option value="" disabled>Choose a scenario</option><option value="cancel">Cancel flow (ORD-103)</option><option value="lookup">Lookup flow (ORD-101)</option><option value="session_limit">Session limit with summary</option><option value="session_limit_without_summary">Session limit without summary</option><option value="fatal_error">Fatal error</option><option value="recoverable_error">Recoverable error mid-call</option><option value="user_ended_no_summary">User ended, no summary</option></select></label></div>}
        </div>
      </section>
      <section className="flex min-w-0 flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-sm lg:min-h-[730px]" aria-labelledby="conversation-title">
        <div className="flex items-center justify-between border-b border-border px-5 py-5 sm:px-[29px]"><div>{state.status.state === 'live' && <span className="text-[13px] font-bold tracking-[.16em] text-muted-foreground">LIVE CALL</span>}<h2 id="conversation-title" className="mt-1 font-heading text-[28px] sm:text-[30px]">Your conversation</h2></div><span className="flex items-center gap-2 rounded-full border border-border px-2.5 py-2 text-sm text-muted-foreground"><i className={`size-1.5 rounded-full ${voiceState === 'live' ? 'bg-green-700' : 'bg-border'}`} />{voiceState === 'live' ? 'In call' : labels[voiceState]}</span></div>
        {sessionLimit && <Alert className="mx-4 mt-4 w-auto min-w-0 max-w-[calc(100%-2rem)] border-amber-300 bg-amber-50 text-amber-950 sm:mx-7"><AlertCircle /><AlertDescription>This call ended because its time limit was reached.</AlertDescription></Alert>}
        {errorMessage && <Alert variant="destructive" className="mx-4 mt-4 w-auto min-w-0 max-w-[calc(100%-2rem)] text-[var(--error-ink)] [&_[data-slot=alert-description]]:text-current sm:mx-7"><AlertCircle /><AlertDescription>{errorMessage}</AlertDescription></Alert>}
        <ScrollArea className="min-h-[300px] flex-1 overflow-hidden px-4 py-5 sm:px-7" ref={transcriptRef} aria-live="polite"><div className="min-w-0">
          {state.turns.length === 0 && <div className="mx-auto flex min-h-[300px] max-w-[420px] flex-col items-center justify-center text-center"><div className="mb-4 grid size-11 place-items-center rounded-full bg-muted text-primary"><Sparkles size={19} /></div><h3 className="mb-2 font-heading text-xl">Your conversation will appear here</h3><p className="text-sm leading-relaxed text-muted-foreground">When you start a call, Aria's replies and helpful order details will show up in this space.</p><div className="mt-6 w-full text-left"><div className="mb-3 flex items-baseline justify-between"><h3 className="font-heading text-lg">Try one of these orders</h3><span className="text-sm text-muted-foreground">Sample data</span></div><ul className="grid gap-3">{orders.map(({ Icon, tone, ...order }) => <li key={order.id} className="pointer-events-none rounded-[20px] border border-border bg-card p-4 shadow-sm"><div className="flex items-center justify-between gap-2"><span className="rounded-full bg-muted px-2.5 py-1 font-mono text-sm">{order.id}</span><Badge className={`h-auto gap-1.5 px-2.5 py-1.5 text-sm ${tone === 'sage' ? 'bg-[#e3eadf] text-primary' : tone === 'success' ? 'bg-[var(--success)] text-[var(--success-ink)]' : 'bg-[var(--warning)] text-[var(--warning-ink)]'}`}><Icon size={15} />{order.status}</Badge></div><p className="mt-2 text-base">{order.product}</p><p className="mt-1 text-sm text-muted-foreground">{order.detail}</p><p className="mt-1 text-sm text-muted-foreground">Try saying: &quot;{order.hint}&quot;</p></li>)}</ul></div></div>}
          {state.turns.map((turn) => <div className={`mb-5 flex max-w-[96%] gap-3 animate-in fade-in slide-in-from-bottom-2 duration-250 motion-reduce:animate-none ${turn.role === 'user' ? 'ml-auto flex-row-reverse' : ''}`} key={turn.turn_id}><div className="grid size-[29px] shrink-0 place-items-center rounded-full bg-muted text-sm text-primary">{turn.role === 'user' ? 'Y' : <Leaf size={14} />}</div><div className="min-w-0"><div className={`mb-1.5 mt-0.5 flex items-center gap-2 text-sm ${turn.role === 'user' ? 'justify-end' : ''}`}><strong>{turn.role === 'user' ? 'You' : 'Aria'}</strong>{turn.interrupted && <span className="rounded-full bg-amber-100 px-2 py-1 text-sm text-amber-950">Interrupted</span>}</div><div className={`break-words rounded-[4px_16px_16px] bg-muted p-3.5 text-base leading-relaxed ${turn.role === 'user' ? 'rounded-[16px_4px_16px_16px]' : ''}`}>{turn.text}</div>{turn.role === 'aria' && turn.turn_id === [...state.turns].reverse().find((item) => item.role === 'aria')?.turn_id && state.tools.filter((tool) => tool.name === 'get_order_details').map((tool) => <OrderResult key={tool.call_id} tool={tool} />)}</div></div>)}
        </div></ScrollArea>
        {debug && <div className="mx-4 mb-3 max-h-24 overflow-auto rounded border border-border bg-muted p-2 font-mono text-sm text-muted-foreground sm:mx-7" aria-label="Tool event log">{state.tools.length ? state.tools.map((tool) => <div key={tool.call_id}>{tool.call_id}: {tool.result == null ? 'pending' : tool.result.ok === false ? 'failed' : 'complete'}</div>) : 'No tool events'}</div>}
        <footer className="border-t border-border px-5 py-3 text-sm text-muted-foreground sm:px-[29px]">Aria answers questions about Aura orders. Sample data shown.</footer>
      </section>
    </div>}
  </main>
}
export default App
