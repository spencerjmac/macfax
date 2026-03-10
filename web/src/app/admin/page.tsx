'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { format } from 'date-fns';

const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

// ── Types ──────────────────────────────────────────────────────────────────────

interface UserInfo {
  username: string;
  is_staff: boolean;
  is_superuser: boolean;
}

interface Season {
  id: number;
  year: number;
  display_name: string;
  is_current: boolean;
}

interface PipelineConfig {
  adj_ratings_iterations: number;
  adj_ratings_convergence: number;
  adj_ratings_shrinkage_floor: number;
  adj_ratings_shrinkage_ceiling: number;
  adj_ratings_shrinkage_decay: number;
  adj_ff_iterations: number;
  ffi_weight_efg: number;
  ffi_weight_tov: number;
  ffi_weight_reb: number;
  ffi_weight_ftr: number;
  ffi_scale_midpoint: number;
  ffi_scale_multiplier: number;
  sor_trials: number;
  sor_baseline_rank_min: number;
  sor_baseline_rank_max: number;
  sor_fallback_rank_min: number;
  sor_fallback_rank_max: number;
  wab_bubble_rank: number;
  sos_baseline_adjem: number;
  sos_logistic_sigma: number;
  sos_home_advantage: number;
  sos_away_penalty: number;
  fallback_hca: number;
  fallback_sigma: number;
  fallback_avg_ortg: number;
}

const DEFAULT_CONFIG: PipelineConfig = {
  adj_ratings_iterations: 25,
  adj_ratings_convergence: 0.001,
  adj_ratings_shrinkage_floor: 170,
  adj_ratings_shrinkage_ceiling: 300,
  adj_ratings_shrinkage_decay: 6.25,
  adj_ff_iterations: 3,
  ffi_weight_efg: 0.4069,
  ffi_weight_tov: 0.4069,
  ffi_weight_reb: 0.1432,
  ffi_weight_ftr: 0.0428,
  ffi_scale_midpoint: 50,
  ffi_scale_multiplier: 20,
  sor_trials: 10000,
  sor_baseline_rank_min: 20,
  sor_baseline_rank_max: 30,
  sor_fallback_rank_min: 15,
  sor_fallback_rank_max: 35,
  wab_bubble_rank: 45,
  sos_baseline_adjem: 0.0,
  sos_logistic_sigma: 10.0,
  sos_home_advantage: 1.5,
  sos_away_penalty: 1.5,
  fallback_hca: 1.85,
  fallback_sigma: 11.08,
  fallback_avg_ortg: 108.0,
};

interface Job {
  id: number;
  job_id: string;
  job_type: string;
  status: string;
  progress_percent: number;
  season_display: string | null;
  parameters: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
  created_by: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function lineClass(line: string): string {
  if (/\[OK\]|✓|SUCCESS|successfully|All data updated/i.test(line))
    return 'text-green-400';
  if (/\[FAIL\]|ERROR|Failed|Traceback/i.test(line)) return 'text-red-400';
  if (/\[WARN\]|WARNING|warning/i.test(line)) return 'text-yellow-400';
  if (/\[SKIP\]/.test(line)) return 'text-gray-500';
  if (/^={3,}|CBB ANALYTICS|UPDATE COMPLETE/.test(line))
    return 'text-blue-300 font-semibold';
  if (/^\[/.test(line)) return 'text-cyan-300';
  return 'text-gray-300';
}

function statusBadge(s: string) {
  const cls: Record<string, string> = {
    running: 'bg-blue-500 text-white animate-pulse',
    success: 'bg-green-600 text-white',
    failed: 'bg-red-600 text-white',
    cancelled: 'bg-yellow-500 text-white',
    pending: 'bg-gray-400 text-white',
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cls[s] ?? 'bg-gray-300 text-gray-900'}`}
    >
      {s}
    </span>
  );
}

function apiFetch(path: string, opts: RequestInit = {}) {
  return fetch(`${API}${path}`, { credentials: 'include', ...opts });
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function AdminPage() {
  // auth
  const [user, setUser] = useState<UserInfo | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState('');
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [authError, setAuthError] = useState('');

  // form
  const [season, setSeason] = useState('');
  const [days, setDays] = useState('');
  const [skipIngest, setSkipIngest] = useState(false);
  const [iterations, setIterations] = useState(25);
  const [sorTrials, setSorTrials] = useState(10000);
  const [seasons, setSeasons] = useState<Season[]>([]);

  // job execution state
  const [runningJobDbId, setRunningJobDbId] = useState<number | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [startError, setStartError] = useState('');

  // live terminal (capped to avoid freeze with huge output)
  const MAX_LOG_LINES = 2500;
  const [logLines, setLogLines] = useState<string[]>([]);
  const [streamDisconnected, setStreamDisconnected] = useState(false);
  const termRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const RECONNECT_MAX = 3;
  const RECONNECT_DELAY_MS = 2000;

  // history
  const [jobs, setJobs] = useState<Job[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);

  // pipeline config
  const [config, setConfig] = useState<PipelineConfig>(DEFAULT_CONFIG);
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [configError, setConfigError] = useState('');
  const [configSaved, setConfigSaved] = useState(false);
  const [configOpen, setConfigOpen] = useState<Record<string, boolean>>({});
  const [adminTab, setAdminTab] = useState<'jobs' | 'config'>('jobs');

  // ── Auto-scroll terminal ────────────────────────────────────────────────────
  useEffect(() => {
    if (termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [logLines]);

  // ── Init ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    apiFetch('/api/auth/csrf/')
      .then((r) => r.json())
      .then((d) => setCsrfToken(d.csrfToken || ''))
      .catch(() => {});
    checkAuth();
  }, []);

  useEffect(() => {
    if (!user) return;
    loadSeasons();
    loadJobs();
    loadConfig();
    const iv = setInterval(loadJobs, 5000);
    return () => clearInterval(iv);
  }, [user]);

  // ── Auth ───────────────────────────────────────────────────────────────────
  const checkAuth = async () => {
    setAuthLoading(true);
    try {
      const r = await apiFetch('/api/auth/me/');
      setUser(r.ok ? await r.json() : null);
    } catch {
      setUser(null);
    } finally {
      setAuthLoading(false);
    }
  };

  const login = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError('');
    const r = await apiFetch('/api/auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify(loginForm),
    });
    if (r.ok) {
      await checkAuth();
    } else {
      const d = await r.json();
      setAuthError(d.error || 'Login failed');
    }
  };

  const logout = async () => {
    await apiFetch('/api/auth/logout/', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken },
    });
    setUser(null);
  };

  // ── Data loaders ───────────────────────────────────────────────────────────
  const loadSeasons = async () => {
    const r = await apiFetch('/api/seasons/');
    if (r.ok) {
      const d = await r.json();
      const list: Season[] = d.results ?? d;
      setSeasons(list);
      const current = list.find((s) => s.is_current);
      if (current) setSeason(String(current.year));
    }
  };

  const loadJobs = async () => {
    const r = await apiFetch('/api/jobs/');
    if (r.ok) {
      const d = await r.json();
      setJobs(d.results ?? d);
    }
  };

  // ── SSE stream ─────────────────────────────────────────────────────────────
  // since = line index to resume from (server sends only lines from there; browser sends Last-Event-ID automatically)
  const openStream = useCallback((jobDbId: number, isReattach = false, since?: number) => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    if (isReattach) {
      reconnectAttemptsRef.current = 0;
      if (since == null || since === 0) setLogLines([]);
    }
    setStreamDisconnected(false);
    setJobStatus('running');
    const url =
      since != null && since > 0
        ? `${API}/api/jobs/${jobDbId}/stream/?since=${since}`
        : `${API}/api/jobs/${jobDbId}/stream/`;
    const es = new EventSource(url, { withCredentials: true });
    esRef.current = es;

    es.onmessage = (evt) => {
      const data = JSON.parse(evt.data);
      if (data.type === 'log') {
        setLogLines((prev) => {
          const next = [...prev, data.line as string];
          return next.length > MAX_LOG_LINES ? next.slice(-MAX_LOG_LINES) : next;
        });
      } else if (data.type === 'done') {
        setJobStatus(data.status as string);
        setRunningJobDbId(null);
        setStreamDisconnected(false);
        reconnectAttemptsRef.current = 0;
        es.close();
        esRef.current = null;
        loadJobs();
      } else if (data.type === 'error') {
        setStreamDisconnected(true);
      }
    };

    es.onerror = () => {
      es.close();
      esRef.current = null;
      const attempts = reconnectAttemptsRef.current;
      if (attempts < RECONNECT_MAX) {
        reconnectAttemptsRef.current = attempts + 1;
        setTimeout(() => openStream(jobDbId), RECONNECT_DELAY_MS);
      } else {
        setStreamDisconnected(true);
      }
    };
  }, []);

  // ── Job control ────────────────────────────────────────────────────────────
  const startJob = async () => {
    setStartError('');
    setSubmitting(true);
    setLogLines([]);
    setJobStatus('pending');

    const body: Record<string, unknown> = {
      season: parseInt(season),
      skip_ingest: skipIngest,
      iterations,
      sor_trials: sorTrials,
    };
    if (days) body.days = parseInt(days);

    const r = await apiFetch('/api/jobs/run/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify(body),
    });

    setSubmitting(false);

    if (r.status === 409) {
      // Another job is running — offer to stream its output
      const d = await r.json();
      setStartError(`Already running: ${d.job_id}. Connecting to its stream…`);
      setRunningJobDbId(d.id);
      openStream(d.id);
      return;
    }

    if (!r.ok) {
      const d = await r.json();
      setStartError(d.error || 'Failed to start job');
      setJobStatus(null);
      return;
    }

    const d = await r.json();
    setRunningJobDbId(d.id);
    openStream(d.id);
  };

  const fixStuck = async () => {
    if (!confirm('Mark all stuck running/pending jobs as failed?')) return;
    setHistoryBusy(true);
    const r = await apiFetch('/api/jobs/fix_stuck/', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken },
    });
    setHistoryBusy(false);
    if (r.ok) {
      const d = await r.json();
      alert(`Fixed ${d.fixed} stuck job(s).`);
      loadJobs();
    }
  };

  const clearHistory = async () => {
    if (!confirm('Delete all completed jobs (success / failed / cancelled)?')) return;
    setHistoryBusy(true);
    const r = await apiFetch('/api/jobs/clear_history/', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken },
    });
    setHistoryBusy(false);
    if (r.ok) {
      const d = await r.json();
      alert(`Deleted ${d.deleted} job(s).`);
      loadJobs();
    }
  };

  // ── Pipeline Config ────────────────────────────────────────────────────────
  const loadConfig = async () => {
    setConfigLoading(true);
    try {
      const r = await apiFetch('/api/pipeline-config/');
      if (r.ok) {
        const d: PipelineConfig = await r.json();
        setConfig(d);
        // Pre-populate the job runner fields from stored config
        setIterations(d.adj_ratings_iterations);
        setSorTrials(d.sor_trials);
      }
    } catch {
      // silently ignore — form stays at defaults
    } finally {
      setConfigLoading(false);
    }
  };

  const saveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setConfigSaving(true);
    setConfigError('');
    setConfigSaved(false);
    try {
      const r = await apiFetch('/api/pipeline-config/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(config),
      });
      if (r.ok) {
        const d: PipelineConfig = await r.json();
        setConfig(d);
        setIterations(d.adj_ratings_iterations);
        setSorTrials(d.sor_trials);
        setConfigSaved(true);
        setTimeout(() => setConfigSaved(false), 3000);
      } else {
        const d = await r.json();
        setConfigError(JSON.stringify(d));
      }
    } catch (err) {
      setConfigError(String(err));
    } finally {
      setConfigSaving(false);
    }
  };

  const cfgNum = (field: keyof PipelineConfig) => ({
    type: 'number' as const,
    step: 'any',
    value: config[field],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setConfig((prev) => ({ ...prev, [field]: parseFloat(e.target.value) || 0 })),
    className:
      'w-full px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm text-white focus:outline-none focus:border-blue-500',
  });

  const cfgInt = (field: keyof PipelineConfig) => ({
    ...cfgNum(field),
    step: '1',
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setConfig((prev) => ({ ...prev, [field]: parseInt(e.target.value, 10) || 0 })),
  });

  const toggleSection = (id: string) =>
    setConfigOpen((prev) => ({ ...prev, [id]: !prev[id] }));

  const ConfigSection = ({
    id, title, children,
  }: {
    id: string;
    title: string;
    children: React.ReactNode;
  }) => (
    <div className="border border-gray-800 rounded">
      <button
        type="button"
        onClick={() => toggleSection(id)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-sm font-medium text-gray-300 hover:bg-gray-800 transition text-left"
      >
        {title}
        <span className="text-gray-500 text-xs">{configOpen[id] ? '▲' : '▼'}</span>
      </button>
      {configOpen[id] && (
        <div className="px-4 pb-4 pt-2 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-gray-800">
          {children}
        </div>
      )}
    </div>
  );

  const Field = ({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) => (
    <div>
      <label className="block text-xs text-gray-400 mb-0.5">{label}</label>
      {children}
      {help && <p className="text-xs text-gray-600 mt-0.5">{help}</p>}
    </div>
  );

  const deleteJob = async (jobId: number) => {
    const r = await apiFetch(`/api/jobs/${jobId}/`, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': csrfToken },
    });
    if (r.ok || r.status === 204) loadJobs();
  };

  const cancelJob = async () => {
    if (!runningJobDbId) return;
    const r = await apiFetch(`/api/jobs/${runningJobDbId}/cancel/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken },
    });
    if (r.ok) {
      setJobStatus('cancelled');
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      setRunningJobDbId(null);
      loadJobs();
    }
  };

  // ── Views ──────────────────────────────────────────────────────────────────
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400">
        Loading…
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
        <div className="w-full max-w-sm bg-gray-900 border border-gray-800 rounded-lg p-8">
          <h1 className="text-xl font-bold text-white mb-1">Pipeline Admin</h1>
          <p className="text-gray-400 text-sm mb-6">Sign in with your Django admin credentials.</p>
          <form onSubmit={login} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Username</label>
              <input
                type="text"
                value={loginForm.username}
                onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
                required
                autoFocus
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Password</label>
              <input
                type="password"
                value={loginForm.password}
                onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
                required
              />
            </div>
            {authError && <p className="text-red-400 text-sm">{authError}</p>}
            <button
              type="submit"
              className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded text-sm font-medium transition"
            >
              Sign In
            </button>
          </form>
        </div>
      </div>
    );
  }

  const isRunning = jobStatus === 'running' || jobStatus === 'pending';

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <span className="font-bold text-white">Pipeline Admin</span>
          <a
            href={`${API}/api/admin/`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-gray-400 hover:text-gray-200 transition"
          >
            Django Admin ↗
          </a>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-400">
            {user.username}
            {user.is_superuser && (
              <span className="ml-1 text-xs text-yellow-400">superuser</span>
            )}
          </span>
          <button
            onClick={logout}
            className="text-gray-400 hover:text-white transition text-xs"
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Tab bar */}
      <div className="border-b border-gray-800">
        <nav className="flex gap-0 px-6">
          <button
            type="button"
            onClick={() => setAdminTab('jobs')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition ${
              adminTab === 'jobs'
                ? 'border-blue-500 text-white'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            Jobs
          </button>
          <button
            type="button"
            onClick={() => setAdminTab('config')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition ${
              adminTab === 'config'
                ? 'border-blue-500 text-white'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            Pipeline Config
          </button>
        </nav>
      </div>

      {adminTab === 'jobs' && (
        <>
      <div className="flex h-[calc(60vh-49px)]">
        {/* ── Left panel: controls ─────────────────────────────────────── */}
        <aside className="w-72 flex-shrink-0 border-r border-gray-800 p-5 overflow-y-auto">
          <h2 className="text-sm font-semibold text-gray-300 mb-4 uppercase tracking-wide">
            Run Update All
          </h2>

          <div className="space-y-4">
            {/* Season */}
            <div>
              <label className="block text-xs text-gray-400 mb-1">Season</label>
              <select
                value={season}
                onChange={(e) => setSeason(e.target.value)}
                disabled={isRunning}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
              >
                <option value="">Select season</option>
                {seasons.map((s) => (
                  <option key={s.id} value={s.year}>
                    {s.display_name}
                  </option>
                ))}
              </select>
            </div>

            {/* Last N days */}
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                Last N days{' '}
                <span className="text-gray-600">(blank = full season)</span>
              </label>
              <input
                type="number"
                value={days}
                onChange={(e) => setDays(e.target.value)}
                disabled={isRunning || skipIngest}
                placeholder="e.g. 3"
                min="1"
                max="30"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 disabled:opacity-50"
              />
            </div>

            {/* Skip ingest */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={skipIngest}
                onChange={(e) => {
                  setSkipIngest(e.target.checked);
                  if (e.target.checked) setDays('');
                }}
                disabled={isRunning}
                className="h-4 w-4 rounded border-gray-600 bg-gray-800 text-blue-500"
              />
              <span className="text-sm text-gray-300">Skip game ingestion</span>
            </label>

            {/* Advanced */}
            <details className="group">
              <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 select-none">
                Advanced options
              </summary>
              <div className="mt-3 space-y-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">
                    Iterations
                  </label>
                  <input
                    type="number"
                    value={iterations}
                    onChange={(e) => setIterations(parseInt(e.target.value))}
                    disabled={isRunning}
                    min="1"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">
                    SOR Trials
                  </label>
                  <input
                    type="number"
                    value={sorTrials}
                    onChange={(e) => setSorTrials(parseInt(e.target.value))}
                    disabled={isRunning}
                    min="100"
                    step="1000"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                  />
                </div>
              </div>
            </details>

            {startError && (
              <p className="text-xs text-yellow-400">{startError}</p>
            )}

            {/* Run / Abort */}
            {isRunning ? (
              <button
                onClick={cancelJob}
                className="w-full bg-red-700 hover:bg-red-600 text-white py-2 rounded text-sm font-medium transition"
              >
                Abort Job
              </button>
            ) : (
              <button
                onClick={startJob}
                disabled={submitting || !season}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded text-sm font-medium transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {submitting ? 'Starting…' : 'Run Pipeline'}
              </button>
            )}

            {/* Status pill */}
            {jobStatus && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">Status:</span>
                {statusBadge(jobStatus)}
              </div>
            )}
          </div>
        </aside>

        {/* ── Right panel: terminal ────────────────────────────────────── */}
        <main className="flex-1 flex flex-col min-w-0">
          {/* Terminal header */}
          <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-800 bg-gray-900">
            <div className="flex gap-1.5">
              <span className="w-3 h-3 rounded-full bg-red-500 opacity-70" />
              <span className="w-3 h-3 rounded-full bg-yellow-500 opacity-70" />
              <span className="w-3 h-3 rounded-full bg-green-500 opacity-70" />
            </div>
            <span className="text-xs text-gray-500 font-mono">
              manage.py update_all
              {season ? ` --season ${season}` : ''}
              {days && !skipIngest ? ` --days ${days}` : ''}
              {skipIngest ? ' --skip-ingest' : ''}
            </span>
            {logLines.length > 0 && (
              <button
                onClick={() => setLogLines([])}
                className="ml-auto text-xs text-gray-600 hover:text-gray-400 transition"
              >
                Clear
              </button>
            )}
          </div>

          {streamDisconnected && runningJobDbId !== null && (
            <div className="flex items-center justify-between gap-4 px-4 py-2 bg-amber-900/50 border-b border-amber-700/50">
              <span className="text-sm text-amber-200">
                Stream disconnected. Job may still be running.
              </span>
              <button
                type="button"
                onClick={() => openStream(runningJobDbId!, true, logLines.length)}
                className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded text-sm font-medium transition"
              >
                Reattach
              </button>
            </div>
          )}

          {/* Terminal body */}
          <div
            ref={termRef}
            className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-5 bg-gray-950"
          >
            {logLines.length === 0 ? (
              <p className="text-gray-700">
                {isRunning
                  ? 'Waiting for output…'
                  : 'Output will appear here when you run the pipeline.'}
              </p>
            ) : (
              <>
                {logLines.length >= MAX_LOG_LINES && (
                  <p className="text-gray-500 mb-1 sticky top-0 bg-gray-950/90 py-1">
                    … showing last {MAX_LOG_LINES} lines
                  </p>
                )}
                {logLines.map((line, i) => (
                  <div key={i} className={lineClass(line)}>
                    {line || '\u00a0'}
                  </div>
                ))}
              </>
            )}
            {isRunning && (
              <div className="mt-1 text-gray-600 animate-pulse">▌</div>
            )}
          </div>
        </main>
      </div>
      </>
      )}

      {adminTab === 'config' && (
      <section className="border-t border-gray-800 px-6 pb-6">
        <div className="py-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Pipeline Configuration
          </h2>
          {configLoading && <span className="text-xs text-gray-500">Loading…</span>}
        </div>
        <form onSubmit={saveConfig} className="px-6 pb-6 space-y-3">
          <ConfigSection id="adj-ratings" title="Adjusted Ratings">
            <Field label="Iterations" help="Max solver iterations">
              <input {...cfgInt('adj_ratings_iterations')} />
            </Field>
            <Field label="Convergence" help="Max AdjEM Δ to stop">
              <input {...cfgNum('adj_ratings_convergence')} />
            </Field>
            <Field label="Shrinkage Floor" help="Min k (possessions)">
              <input {...cfgInt('adj_ratings_shrinkage_floor')} />
            </Field>
            <Field label="Shrinkage Ceiling" help="Max k (possessions)">
              <input {...cfgInt('adj_ratings_shrinkage_ceiling')} />
            </Field>
            <Field label="Shrinkage Decay" help="k drop per avg game">
              <input {...cfgNum('adj_ratings_shrinkage_decay')} />
            </Field>
          </ConfigSection>

          <ConfigSection id="adj-ff" title="Adjusted Four Factors">
            <Field label="Iterations">
              <input {...cfgInt('adj_ff_iterations')} />
            </Field>
          </ConfigSection>

          <ConfigSection id="ffi" title="Four Factor Index">
            <Field label="eFG% Weight" help="Weights should sum to 1.0">
              <input {...cfgNum('ffi_weight_efg')} />
            </Field>
            <Field label="TOV Edge Weight">
              <input {...cfgNum('ffi_weight_tov')} />
            </Field>
            <Field label="Rebounding Weight">
              <input {...cfgNum('ffi_weight_reb')} />
            </Field>
            <Field label="FTR Weight">
              <input {...cfgNum('ffi_weight_ftr')} />
            </Field>
            <Field label="Scale Midpoint" help="Output center (default 50)">
              <input {...cfgInt('ffi_scale_midpoint')} />
            </Field>
            <Field label="Scale Multiplier" help="z-score multiplier (default 20)">
              <input {...cfgInt('ffi_scale_multiplier')} />
            </Field>
          </ConfigSection>

          <ConfigSection id="sor" title="Strength of Record">
            <Field label="Monte Carlo Trials">
              <input {...cfgInt('sor_trials')} />
            </Field>
            <Field label="Baseline Rank Min" help="Primary range start">
              <input {...cfgInt('sor_baseline_rank_min')} />
            </Field>
            <Field label="Baseline Rank Max" help="Primary range end">
              <input {...cfgInt('sor_baseline_rank_max')} />
            </Field>
            <Field label="Fallback Rank Min">
              <input {...cfgInt('sor_fallback_rank_min')} />
            </Field>
            <Field label="Fallback Rank Max">
              <input {...cfgInt('sor_fallback_rank_max')} />
            </Field>
          </ConfigSection>

          <ConfigSection id="wab" title="WAB / Game Value">
            <Field label="Bubble Team Rank" help="AdjEM rank used as WAB baseline">
              <input {...cfgInt('wab_bubble_rank')} />
            </Field>
          </ConfigSection>

          <ConfigSection id="sos" title="Strength of Schedule">
            <Field label="Baseline AdjEM" help="Average D1 team anchor">
              <input {...cfgNum('sos_baseline_adjem')} />
            </Field>
            <Field label="Logistic Sigma" help="Win-prob spread parameter">
              <input {...cfgNum('sos_logistic_sigma')} />
            </Field>
            <Field label="Home Advantage (pts)">
              <input {...cfgNum('sos_home_advantage')} />
            </Field>
            <Field label="Away Penalty (pts)">
              <input {...cfgNum('sos_away_penalty')} />
            </Field>
          </ConfigSection>

          <ConfigSection id="fallbacks" title="Shared Fallbacks">
            <Field label="Fallback HCA (pts)" help="Used before compute_hca runs">
              <input {...cfgNum('fallback_hca')} />
            </Field>
            <Field label="Fallback Sigma" help="Used before compute_sigma runs">
              <input {...cfgNum('fallback_sigma')} />
            </Field>
            <Field label="Fallback Avg ORtg" help="Used before compute_national_averages runs">
              <input {...cfgNum('fallback_avg_ortg')} />
            </Field>
          </ConfigSection>

          <div className="flex items-center gap-4 pt-2">
            <button
              type="submit"
              disabled={configSaving}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded font-medium disabled:opacity-50 transition"
            >
              {configSaving ? 'Saving…' : 'Save Configuration'}
            </button>
            {configSaved && (
              <span className="text-green-400 text-sm">Saved successfully.</span>
            )}
            {configError && (
              <span className="text-red-400 text-sm">{configError}</span>
            )}
          </div>
        </form>
      </section>
      )}

      {adminTab === 'jobs' && (
      <section className="border-t border-gray-800">
        <div className="px-6 py-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Job History
            <span className="ml-2 text-gray-600 font-normal normal-case">
              {jobs.length} jobs
            </span>
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={fixStuck}
              disabled={historyBusy}
              className="text-xs px-3 py-1.5 rounded bg-yellow-900 hover:bg-yellow-800 text-yellow-200 disabled:opacity-40 transition"
              title="Mark all running/pending jobs as failed (use after a crash)"
            >
              Fix Stuck
            </button>
            <button
              onClick={clearHistory}
              disabled={historyBusy}
              className="text-xs px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 disabled:opacity-40 transition"
            >
              Clear History
            </button>
          </div>
        </div>
        <div className="overflow-x-auto max-h-60 overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-gray-900">
              <tr className="text-gray-500 text-left">
                <th className="px-6 py-2 font-medium">Job ID</th>
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Season</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Started</th>
                <th className="px-4 py-2 font-medium">Duration</th>
                <th className="px-4 py-2 font-medium">By</th>
                <th className="px-4 py-2 font-medium">Stream</th>
                <th className="px-4 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-6 text-center text-gray-600">
                    No jobs yet.
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-900 transition">
                    <td className="px-6 py-2 font-mono text-gray-500">
                      {job.job_id.slice(0, 16)}…
                    </td>
                    <td className="px-4 py-2 text-gray-300">{job.job_type}</td>
                    <td className="px-4 py-2 text-gray-400">
                      {job.season_display ?? '—'}
                    </td>
                    <td className="px-4 py-2">{statusBadge(job.status)}</td>
                    <td className="px-4 py-2 text-gray-500">
                      {format(new Date(job.started_at), 'MMM d HH:mm')}
                    </td>
                    <td className="px-4 py-2 text-gray-500">
                      {job.duration_seconds != null
                        ? `${(job.duration_seconds / 60).toFixed(1)}m`
                        : '—'}
                    </td>
                    <td className="px-4 py-2 text-gray-600">{job.created_by}</td>
                    <td className="px-4 py-2">
                      {job.status === 'running' && (
                        <button
                          onClick={() => {
                            setLogLines([]);
                            setRunningJobDbId(job.id);
                            openStream(job.id);
                          }}
                          className="text-blue-400 hover:text-blue-300 transition"
                        >
                          Attach
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {job.status !== 'running' && job.status !== 'pending' && (
                        <button
                          onClick={() => deleteJob(job.id)}
                          className="text-gray-600 hover:text-red-400 transition"
                          title="Delete this job"
                        >
                          ✕
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
      )}
    </div>
  );
}
