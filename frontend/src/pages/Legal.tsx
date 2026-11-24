import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api } from '../lib/api'

const UPDATED = '24 November 2026'

function Page({ title, children }: { title: string; children: ReactNode }) {
  useEffect(() => { document.title = `${title} · TravelGenie` }, [title])
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-8">
        <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
          <ArrowLeft className="size-4" /> TravelGenie
        </Link>
        <h1 className="mt-4 font-serif text-4xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-faint">Last updated {UPDATED}</p>
        <div className="answer prose prose-sm mt-8 max-w-none sm:prose-base">{children}</div>
        <p className="mt-10 border-t border-line pt-4 text-sm text-muted">
          See also: <Link to="/privacy" className="text-accent hover:underline">Privacy Policy</Link> ·{' '}
          <Link to="/terms" className="text-accent hover:underline">Terms of Use</Link>
        </p>
      </div>
    </div>
  )
}

function useContact() {
  const [email, setEmail] = useState<string | null>(null)
  useEffect(() => { api.authConfig().then(c => setEmail(c.contact_email ?? null)).catch(() => {}) }, [])
  return email
}

export function PrivacyPolicy() {
  const contact = useContact()
  return (
    <Page title="Privacy Policy">
      <p>
        This policy explains what personal data TravelGenie collects, why, who it is shared with, and the
        rights you have, including under India's Digital Personal Data Protection Act, 2023 (DPDP Act).
      </p>

      <h2>What we collect</h2>
      <ul>
        <li><strong>Account:</strong> your name, email address and a one-way hash of your password (we never store the password itself). If you use Google sign-in: your Google account ID and profile photo URL.</li>
        <li><strong>Preferences you set:</strong> home city, currency, usual number of travellers, budget range, interests, dietary needs, pace and theme.</li>
        <li><strong>Your trips:</strong> what you ask the assistant, its replies, and the plans it creates.</li>
        <li><strong>Documents you upload:</strong> the text extracted from them (for example a booking confirmation).</li>
        <li><strong>Usage counts:</strong> how many AI requests you made each day, to enforce fair-use limits.</li>
        <li><strong>Consent:</strong> the date you accepted this policy and the Terms of Use.</li>
      </ul>
      <p>We do not collect payment details, government IDs, precise location or contacts, and we do not use advertising trackers.</p>

      <h2>Why we use it</h2>
      <ul>
        <li>To provide the service: create and save your trip plans, remember your conversations and preferences.</li>
        <li>To keep the service safe and available: sign-in, fair-use limits and fixing errors.</li>
      </ul>
      <p>We do not sell your personal data or use it for advertising.</p>

      <h2>Who processes it for us</h2>
      <p>To work, TravelGenie sends limited data to these service providers:</p>
      <ul>
        <li><strong>Groq:</strong> your messages and trip details, to generate plans and answers with AI models.</li>
        <li><strong>Jina AI:</strong> search queries and the text of documents you upload, to make them searchable.</li>
        <li><strong>Neon:</strong> hosts the database where your account, trips and conversations are stored.</li>
        <li><strong>Vercel:</strong> hosts the website and runs the app.</li>
        <li><strong>OpenWeatherMap, Wikivoyage and OpenStreetMap:</strong> only destination and city names, to fetch weather, places and maps.</li>
      </ul>
      <p>These providers may process data outside India.</p>

      <h2>Sharing and privacy within the app</h2>
      <ul>
        <li>Documents you upload are <strong>private to you</strong>: they are only used in your own answers.</li>
        <li>A trip plan becomes visible to others only if you create a share link. Shared pages never include your conversation or uploaded documents, and you can stop sharing at any time.</li>
      </ul>

      <h2>How long we keep it</h2>
      <p>
        We keep your data while your account exists. Deleting a trip deletes its plan and conversation.
        Deleting your account permanently deletes your account, preferences, trips, conversations and uploaded
        documents. Short-lived technical caches and service logs expire on their own.
      </p>

      <h2>Your rights</h2>
      <ul>
        <li><strong>Access:</strong> download all your data any time from <em>Settings → Your data</em>.</li>
        <li><strong>Correction:</strong> update your name and preferences in <em>Settings</em>.</li>
        <li><strong>Erasure:</strong> delete trips, or your whole account, in the app.</li>
        <li><strong>Withdraw consent:</strong> delete your account; we then stop processing your data.</li>
        <li><strong>Grievances:</strong> contact us below; we aim to respond within 30 days.</li>
      </ul>

      <h2>Security</h2>
      <p>
        Passwords are hashed with bcrypt, sessions use secure, httpOnly cookies, connections are encrypted (HTTPS),
        and every request is checked so you can only access your own data.
      </p>

      <h2>Children</h2>
      <p>TravelGenie is intended for people aged 18 and over.</p>

      <h2>Contact</h2>
      <p>
        For privacy questions, data requests or grievances:{' '}
        {contact ? <a href={`mailto:${contact}`}>{contact}</a> : <span>the TravelGenie team (contact details are shown here once configured)</span>}.
      </p>
    </Page>
  )
}

export function TermsOfUse() {
  return (
    <Page title="Terms of Use">
      <p>By creating an account or using TravelGenie you agree to these terms.</p>

      <h2>What TravelGenie is</h2>
      <p>
        TravelGenie is an AI-powered trip-planning assistant. It suggests itineraries, places to stay, sights,
        ways to travel and estimated costs, using AI models and public sources such as Wikivoyage and OpenStreetMap.
      </p>

      <h2>AI suggestions are not guarantees</h2>
      <ul>
        <li>Plans, prices, timings, opening hours and travel rules are <strong>estimates</strong> and can be wrong or out of date.</li>
        <li>Always confirm prices, availability, visa and permit requirements, and safety advice with official sources and providers before booking or travelling.</li>
        <li>Bookings shown in TravelGenie are <strong>simulated</strong>; nothing is reserved or paid for. Links to booking sites open third-party websites with their own terms.</li>
      </ul>

      <h2>Your account</h2>
      <ul>
        <li>You must be 18 or older and give accurate information.</li>
        <li>Keep your password safe; you are responsible for activity on your account.</li>
      </ul>

      <h2>Fair use</h2>
      <ul>
        <li>Each account has a daily limit on AI requests so the service stays available for everyone.</li>
        <li>Don't misuse the service: no automated scraping, attempts to break security, or illegal, harmful or abusive content.</li>
        <li>Only upload documents you have the right to use.</li>
      </ul>

      <h2>Your content</h2>
      <p>
        You own what you write and upload. You allow TravelGenie to process it only to provide the service, as
        described in the <Link to="/privacy">Privacy Policy</Link>. If you share a trip link, anyone with the link
        can view that plan.
      </p>

      <h2>Availability and liability</h2>
      <p>
        TravelGenie is provided "as is", without warranties. We may change, pause or stop features. To the extent
        permitted by law, we are not liable for losses arising from reliance on AI-generated suggestions or from
        third-party services.
      </p>

      <h2>Ending your use</h2>
      <p>You can delete your account at any time in Settings. We may suspend accounts that break these terms.</p>

      <h2>Governing law</h2>
      <p>These terms are governed by the laws of India.</p>

      <h2>Changes</h2>
      <p>We may update these terms; the date above shows the latest version.</p>
    </Page>
  )
}
