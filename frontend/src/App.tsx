import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type Role = 'patient' | 'provider'
type Status = 'pending' | 'confirmed' | 'cancelled'

type Appointment = {
  id: number
  patient_name: string
  patient_email: string
  provider_id: number
  appointment_type: string
  reason: string
  scheduled_start: string
  scheduled_end: string
  status: Status
  version: number
}

type RequestForm = {
  scheduled_start: string
  appointment_type: string
  reason: string
}

const API_URL = 'http://127.0.0.1:8000/api'
const patientEmail = 'jordan@example.com'
const providerId = 1

class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new ApiError(response.status, body.detail ?? 'Something went wrong.')
  return body as T
}

function localInputValue(iso: string) { return iso.slice(0, 16) }

function dateLabel(iso: string) {
  return new Intl.DateTimeFormat('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(iso))
}

function timeLabel(iso: string) {
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date(iso))
}

function App() {
  const [role, setRole] = useState<Role>('patient')
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [request, setRequest] = useState<RequestForm>({
    scheduled_start: localInputValue(new Date(Date.now() + 86400000 * 2).toISOString()),
    appointment_type: 'Therapy follow-up',
    reason: '',
  })
  const [rescheduleDrafts, setRescheduleDrafts] = useState<Record<number, string>>({})

  async function loadAppointments() {
    setLoading(true)
    setError('')
    try {
      const filter = role === 'patient' ? `?patient_email=${encodeURIComponent(patientEmail)}` : `?provider_id=${providerId}`
      setAppointments(await apiRequest<Appointment[]>(`/appointments${filter}`))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load appointments.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadAppointments() }, [role])

  async function runAction(action: () => Promise<Appointment>, successMessage: string) {
    setError('')
    setMessage('')
    try {
      await action()
      setMessage(successMessage)
      await loadAppointments()
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 409) {
        setError(`${requestError.message} The list has been refreshed.`)
        await loadAppointments()
      } else {
        setError(requestError instanceof Error ? requestError.message : 'Unable to update appointment.')
      }
    }
  }

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setMessage('')
    try {
      await apiRequest<Appointment>('/appointments', {
        method: 'POST',
        body: JSON.stringify({
          patient_name: 'Jordan Lee', patient_email: patientEmail, provider_id: providerId,
          appointment_type: request.appointment_type, reason: request.reason,
          scheduled_start: new Date(request.scheduled_start).toISOString(), duration_minutes: 60,
        }),
      })
      setRequest((current) => ({ ...current, reason: '' }))
      setMessage('Your appointment request was submitted.')
      await loadAppointments()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to submit request.')
    } finally { setSubmitting(false) }
  }

  function cancel(appointment: Appointment) {
    if (!window.confirm('Cancel this confirmed appointment?')) return
    void runAction(
      () => apiRequest<Appointment>(`/appointments/${appointment.id}/cancel`, { method: 'POST', body: JSON.stringify({ version: appointment.version }) }),
      'Appointment cancelled.',
    )
  }

  function confirm(appointment: Appointment) {
    void runAction(
      () => apiRequest<Appointment>(`/appointments/${appointment.id}/confirm`, { method: 'POST', body: JSON.stringify({ version: appointment.version }) }),
      'Appointment confirmed. The patient notification was queued.',
    )
  }

  function reschedule(appointment: Appointment) {
    const scheduledStart = rescheduleDrafts[appointment.id]
    if (!scheduledStart) return
    void runAction(
      () => apiRequest<Appointment>(`/appointments/${appointment.id}/reschedule`, {
        method: 'POST', body: JSON.stringify({ version: appointment.version, scheduled_start: new Date(scheduledStart).toISOString(), duration_minutes: 60 }),
      }),
      'Appointment time updated.',
    )
  }

  return (
    <main className="portal-shell">
      <header className="topbar">
        <div className="brand-mark" aria-label="Harbor Health home">HH</div>
        <div className="brand-copy"><span className="eyebrow">Harbor Health</span><span className="brand-name">Patient portal</span></div>
        <div className="role-switcher" aria-label="Choose portal role">
          <button className={role === 'patient' ? 'active' : ''} onClick={() => setRole('patient')} type="button">Patient</button>
          <button className={role === 'provider' ? 'active' : ''} onClick={() => setRole('provider')} type="button">Provider</button>
        </div>
      </header>

      <section className="intro">
        <div><p className="eyebrow accent-text">{role === 'patient' ? 'Your care, in view' : 'Care team workspace'}</p><h1>{role === 'patient' ? 'Appointments' : 'Appointment requests'}</h1><p className="intro-copy">{role === 'patient' ? 'Keep track of upcoming visits and request time with your care team.' : 'Review requests, protect your schedule, and keep patients in the loop.'}</p></div>
        <div className="date-stamp"><span>Today</span><strong>{dateLabel(new Date().toISOString())}</strong></div>
      </section>

      {message && <div className="notice success" role="status">{message}</div>}
      {error && <div className="notice error" role="alert">{error}</div>}

      <section className="content-grid">
        <div className="appointments-panel">
          <div className="section-heading"><div><p className="eyebrow">Schedule</p><h2>{role === 'patient' ? 'Your appointments' : 'Assigned appointments'}</h2></div><button className="refresh-button" type="button" onClick={() => void loadAppointments()} disabled={loading} aria-label="Refresh appointments"><span aria-hidden="true">↻</span> Refresh</button></div>
          {loading ? <div className="empty-state">Loading your schedule...</div> : appointments.length === 0 ? <div className="empty-state">No appointments to show yet.</div> : (
            <div className="appointment-list">
              {appointments.map((appointment) => <article className="appointment-card" key={appointment.id}>
                <div className="appointment-date"><span>{dateLabel(appointment.scheduled_start).split(',')[0]}</span><strong>{new Date(appointment.scheduled_start).getDate()}</strong><span>{new Intl.DateTimeFormat('en-US', { month: 'short' }).format(new Date(appointment.scheduled_start))}</span></div>
                <div className="appointment-details">
                  <div className="appointment-title-row"><h3>{appointment.appointment_type}</h3><span className={`status ${appointment.status}`}>{appointment.status}</span></div>
                  <p className="appointment-time">{timeLabel(appointment.scheduled_start)} - {timeLabel(appointment.scheduled_end)}</p>
                  <p className="appointment-meta">{role === 'patient' ? 'Dr. Maya Patel' : appointment.patient_name} <span>·</span> {appointment.reason}</p>
                  {role === 'patient' && appointment.status === 'confirmed' && <button className="text-button danger-text" type="button" onClick={() => cancel(appointment)}>Cancel appointment</button>}
                  {role === 'provider' && <div className="provider-actions">
                    {appointment.status === 'pending' && <button className="primary-button small" type="button" onClick={() => confirm(appointment)}>Confirm request</button>}
                    {appointment.status !== 'cancelled' && <div className="reschedule-control"><input aria-label={`New time for appointment ${appointment.id}`} type="datetime-local" value={rescheduleDrafts[appointment.id] ?? localInputValue(appointment.scheduled_start)} onChange={(event) => setRescheduleDrafts((current) => ({ ...current, [appointment.id]: event.target.value }))} /><button className="secondary-button small" type="button" onClick={() => reschedule(appointment)}>Move time</button></div>}
                  </div>}
                </div>
              </article>)}
            </div>
          )}
        </div>

        {role === 'patient' ? <aside className="request-panel"><p className="eyebrow">New request</p><h2>Find a time that works</h2><p className="panel-copy">Requests are sent to your care team for confirmation.</p><form onSubmit={submitRequest}><label>Preferred date and time<input required type="datetime-local" value={request.scheduled_start} onChange={(event) => setRequest({ ...request, scheduled_start: event.target.value })} /></label><label>Appointment type<select value={request.appointment_type} onChange={(event) => setRequest({ ...request, appointment_type: event.target.value })}><option>Therapy follow-up</option><option>Medication review</option><option>Initial consultation</option><option>Care planning</option></select></label><label>Reason for visit<textarea required rows={4} placeholder="What would you like to discuss?" value={request.reason} onChange={(event) => setRequest({ ...request, reason: event.target.value })} /></label><button className="primary-button" disabled={submitting} type="submit">{submitting ? 'Sending request...' : 'Request appointment'} <span aria-hidden="true">→</span></button></form></aside> : <aside className="provider-summary"><p className="eyebrow">Today at a glance</p><div className="summary-number">{appointments.filter((appointment) => appointment.status === 'pending').length}</div><h2>Pending requests</h2><p className="panel-copy">Confirm a request or propose a better time. Every change is recorded for the care team.</p><div className="summary-rule" /><p className="small-note"><span className="dot green" /> Notifications are queued after confirmation</p><p className="small-note"><span className="dot amber" /> Conflicting times are blocked automatically</p></aside>}
      </section>
    </main>
  )
}

export default App