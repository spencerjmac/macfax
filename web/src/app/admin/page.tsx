'use client';

import React, { useState, useEffect } from 'react';
import { format } from 'date-fns';

interface DataProcessingJob {
  id: number;
  job_id: string;
  job_type: string;
  job_type_display?: string;
  get_job_type_display?: string;
  status: string;
  status_display?: string;
  get_status_display?: string;
  progress_percent: number;
  season: number | null;
  season_display: string | null;
  parameters: Record<string, any>;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  error_message: string;
  created_by: string;
  is_running: boolean;
  is_complete: boolean;
  logs: string;
  updated_at: string;
}

interface Season {
  id: number;
  year: number;
  display_name: string;
  is_current: boolean;
}

interface UserInfo {
  username: string;
  is_staff: boolean;
  is_superuser: boolean;
}

const AdminDashboard = () => {
  const [jobs, setJobs] = useState<DataProcessingJob[]>([]);
  const [seasons, setSeasons] = useState<Season[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedJob, setSelectedJob] = useState<DataProcessingJob | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [csrfToken, setCsrfToken] = useState<string>('');
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [formData, setFormData] = useState({
    season: '',
    skipIngest: false,
    iterations: 25,
    sorTrials: 10000,
  });

  // Load data on mount
  useEffect(() => {
    const init = async () => {
      await fetchCsrf();
      await loadUser();
    };
    init();
  }, []);

  useEffect(() => {
    if (!user) return;
    loadJobs();
    loadSeasons();

    const interval = setInterval(loadJobs, 2000);
    return () => clearInterval(interval);
  }, [user]);

  const fetchCsrf = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/auth/csrf/`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setCsrfToken(data.csrfToken || '');
      }
    } catch (error) {
      console.error('Failed to fetch CSRF token:', error);
    }
  };

  const loadUser = async () => {
    setAuthLoading(true);
    setAuthError(null);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/auth/me/`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setUser(data);
      } else {
        setUser(null);
      }
    } catch (error) {
      setUser(null);
      setAuthError('Failed to check login status');
    } finally {
      setAuthLoading(false);
    }
  };

  const loadJobs = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/jobs/`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setJobs(data.results || data);
      }
    } catch (error) {
      console.error('Failed to load jobs:', error);
    }
  };

  const loadSeasons = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/seasons/`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setSeasons(data.results || data);
      }
    } catch (error) {
      console.error('Failed to load seasons:', error);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/auth/login/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify(loginForm),
      });

      if (response.ok) {
        await loadUser();
      } else {
        const data = await response.json();
        setAuthError(data.error || 'Login failed');
      }
    } catch (error) {
      setAuthError('Login failed');
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/api/auth/logout/`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
        },
        credentials: 'include',
      });
    } finally {
      setUser(null);
    }
  };

  const handleStartJob = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.season) return;

    setLoading(true);
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL}/api/jobs/start_update_all/`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          credentials: 'include',
          body: JSON.stringify({
            season: parseInt(formData.season),
            skip_ingest: formData.skipIngest,
            iterations: formData.iterations,
            sor_trials: formData.sorTrials,
          }),
        }
      );

      if (response.ok) {
        const job = await response.json();
        setJobs([job, ...jobs]);
        setFormData({ season: '', skipIngest: false, iterations: 25, sorTrials: 10000 });
        alert('Job started successfully!');
      } else {
        alert('Failed to start job');
      }
    } catch (error) {
      alert(`Error: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStartSubjob = async (jobType: string) => {
    if (!formData.season) return;
    setLoading(true);
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL}/api/jobs/start_subjob/`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          credentials: 'include',
          body: JSON.stringify({
            job_type: jobType,
            season: parseInt(formData.season),
            parameters: {
              iterations: formData.iterations,
              sor_trials: formData.sorTrials,
            },
          }),
        }
      );

      if (response.ok) {
        const job = await response.json();
        setJobs([job, ...jobs]);
      } else {
        const data = await response.json();
        alert(data.error || 'Failed to start sub-job');
      }
    } catch (error) {
      alert(`Error: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success':
        return 'text-green-600 bg-green-50';
      case 'failed':
        return 'text-red-600 bg-red-50';
      case 'running':
        return 'text-blue-600 bg-blue-50';
      case 'pending':
        return 'text-yellow-600 bg-yellow-50';
      default:
        return 'text-gray-600 bg-gray-50';
    }
  };

  const getProgressBar = (job: DataProcessingJob) => {
    return (
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div
          className="bg-blue-600 h-2 rounded-full transition-all duration-500"
          style={{ width: `${job.progress_percent}%` }}
        />
      </div>
    );
  };

  const getJobTypeLabel = (job: DataProcessingJob) =>
    job.job_type_display || job.get_job_type_display || job.job_type;

  const getStatusLabel = (job: DataProcessingJob) =>
    job.status_display || job.get_status_display || job.status;

  const statusCounts = jobs.reduce(
    (acc, job) => {
      acc[job.status] = (acc[job.status] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-600">Loading admin...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="w-full max-w-md bg-white rounded-lg shadow p-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Admin Login</h1>
          <p className="text-gray-600 mb-6">Sign in with your backend admin credentials.</p>
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
              <input
                type="text"
                value={loginForm.username}
                onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <input
                type="password"
                value={loginForm.password}
                onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            {authError && (
              <div className="text-sm text-red-600">{authError}</div>
            )}
            <button
              type="submit"
              className="w-full bg-blue-600 text-white py-2 rounded-md font-medium hover:bg-blue-700 transition"
            >
              Sign In
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">📊 Data Pipeline Admin</h1>
              <p className="text-gray-600 mt-2">Monitor and manage data processing jobs</p>
            </div>
            <div className="text-sm text-gray-600">
              <span className="mr-3">Signed in as <strong>{user.username}</strong></span>
              <button onClick={handleLogout} className="text-blue-600 hover:text-blue-700">Sign out</button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Start Job Form */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-bold text-gray-900 mb-4">▶️ Start Update All</h2>
              
              <form onSubmit={handleStartJob} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Season
                  </label>
                  <select
                    value={formData.season}
                    onChange={(e) => setFormData({ ...formData, season: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  >
                    <option value="">Select a season</option>
                    {seasons.map((season) => (
                      <option key={season.id} value={season.year}>
                        {season.display_name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Iterations
                  </label>
                  <input
                    type="number"
                    value={formData.iterations}
                    onChange={(e) => setFormData({ ...formData, iterations: parseInt(e.target.value) })}
                    min="1"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    SOR Trials
                  </label>
                  <input
                    type="number"
                    value={formData.sorTrials}
                    onChange={(e) => setFormData({ ...formData, sorTrials: parseInt(e.target.value) })}
                    min="100"
                    step="100"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.skipIngest}
                    onChange={(e) => setFormData({ ...formData, skipIngest: e.target.checked })}
                    className="h-4 w-4 text-blue-600 border-gray-300 rounded"
                  />
                  <span className="ml-2 text-sm text-gray-700">Skip Game Ingestion</span>
                </label>

                <button
                  type="submit"
                  disabled={loading || !formData.season}
                  className="w-full bg-blue-600 text-white py-2 rounded-md font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition"
                >
                  {loading ? 'Starting...' : 'Start Job'}
                </button>
              </form>

              <div className="mt-6">
                <h3 className="text-sm font-semibold text-gray-900 mb-2">🔁 Reschedule Sub-Jobs</h3>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { key: 'compute_team_metrics', label: 'Team Metrics' },
                    { key: 'compute_adjusted_ratings', label: 'Adjusted Ratings' },
                    { key: 'compute_four_factor_index', label: 'Four Factor Index' },
                    { key: 'fetch_net_rankings', label: 'NET Rankings' },
                    { key: 'compute_sor', label: 'SOR' },
                    { key: 'compute_game_value', label: 'Game Value' },
                    { key: 'compute_sos', label: 'SOS' },
                  ].map((job) => (
                    <button
                      key={job.key}
                      onClick={() => handleStartSubjob(job.key)}
                      disabled={loading || !formData.season}
                      className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-800 py-2 rounded-md border border-gray-200 disabled:bg-gray-50 disabled:text-gray-400"
                    >
                      {job.label}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-500 mt-2">Reschedule a specific step without running the full pipeline.</p>
              </div>

              <div className="mt-6 p-4 bg-blue-50 rounded-md border border-blue-200">
                <p className="text-sm text-blue-800">
                  <strong>ℹ️ Tip:</strong> Jobs run in the background. You can close this page and come back later to check progress.
                </p>
              </div>
            </div>
          </div>

          {/* Job Details / Logs */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow p-6">
              {selectedJob ? (
                <>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold text-gray-900">📋 Job Details</h2>
                    <button
                      onClick={() => setSelectedJob(null)}
                      className="text-gray-500 hover:text-gray-700"
                    >
                      ✕
                    </button>
                  </div>

                  <div className="space-y-4 mb-6">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm text-gray-600">Job ID</p>
                        <p className="font-mono text-sm text-gray-900">{selectedJob.job_id}</p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-600">Status</p>
                        <span className={`inline-block px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(selectedJob.status)}`}>
                          {getStatusLabel(selectedJob)}
                        </span>
                      </div>
                      <div>
                        <p className="text-sm text-gray-600">Started</p>
                        <p className="text-sm text-gray-900">{format(new Date(selectedJob.started_at), 'MMM dd, yyyy HH:mm:ss')}</p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-600">Duration</p>
                        <p className="text-sm text-gray-900">
                          {selectedJob.duration_seconds 
                            ? `${(selectedJob.duration_seconds / 60).toFixed(1)} min`
                            : 'Running...'}
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
                      <div>
                        <p className="text-sm text-gray-600 mb-2">Progress: {selectedJob.progress_percent}%</p>
                        {getProgressBar(selectedJob)}
                      </div>
                      <div className="flex items-center justify-center">
                        <div
                          className="w-24 h-24 rounded-full flex items-center justify-center text-sm font-semibold text-gray-900"
                          style={{
                            background: `conic-gradient(#2563eb ${selectedJob.progress_percent * 3.6}deg, #e5e7eb 0deg)`,
                          }}
                        >
                          <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center">
                            {selectedJob.progress_percent}%
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Logs */}
                  {selectedJob.logs && (
                    <div>
                      <h3 className="font-bold text-gray-900 mb-2">📝 Execution Logs</h3>
                      <div className="bg-gray-900 text-gray-100 p-4 rounded-md font-mono text-xs max-h-96 overflow-y-auto">
                        {selectedJob.logs.split('\n').map((line, i) => (
                          <div key={i} className="text-gray-400">
                            {line || ' '}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {selectedJob.error_message && (
                    <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-md">
                      <p className="text-sm font-bold text-red-800 mb-2">❌ Error</p>
                      <p className="text-sm text-red-700 font-mono">{selectedJob.error_message}</p>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-12">
                  <p className="text-gray-500">Select a job to view details and logs</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Job History Table */}
        <div className="mt-8 bg-white rounded-lg shadow overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-xl font-bold text-gray-900">📜 Job History</h2>
            <div className="flex items-center gap-3 text-xs text-gray-600">
              <span>Running: {statusCounts.running || 0}</span>
              <span>Pending: {statusCounts.pending || 0}</span>
              <span>Success: {statusCounts.success || 0}</span>
              <span>Failed: {statusCounts.failed || 0}</span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left font-medium text-gray-700">Job ID</th>
                  <th className="px-6 py-3 text-left font-medium text-gray-700">Type</th>
                  <th className="px-6 py-3 text-left font-medium text-gray-700">Season</th>
                  <th className="px-6 py-3 text-left font-medium text-gray-700">Status</th>
                  <th className="px-6 py-3 text-left font-medium text-gray-700">Progress</th>
                  <th className="px-6 py-3 text-left font-medium text-gray-700">Started</th>
                  <th className="px-6 py-3 text-left font-medium text-gray-700">Duration</th>
                  <th className="px-6 py-3 text-left font-medium text-gray-700">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {jobs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-6 py-8 text-center text-gray-500">
                      No jobs yet. Start one above to see it appear here.
                    </td>
                  </tr>
                ) : (
                  jobs.map((job) => (
                    <tr key={job.id} className="hover:bg-gray-50">
                      <td className="px-6 py-3 font-mono text-xs text-gray-600">{job.job_id.slice(0, 12)}...</td>
                      <td className="px-6 py-3 text-gray-900">{getJobTypeLabel(job)}</td>
                      <td className="px-6 py-3 text-gray-900">{job.season_display || '-'}</td>
                      <td className="px-6 py-3">
                        <span className={`inline-block px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(job.status)}`}>
                          {getStatusLabel(job)}
                        </span>
                      </td>
                      <td className="px-6 py-3">
                        <div className="w-24">
                          <div className="flex items-center gap-2">
                            <div className="flex-1">{getProgressBar(job)}</div>
                            <span className="text-xs text-gray-600 w-8">{job.progress_percent}%</span>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-3 text-gray-600">
                        {format(new Date(job.started_at), 'MMM dd HH:mm')}
                      </td>
                      <td className="px-6 py-3 text-gray-600">
                        {job.duration_seconds ? `${(job.duration_seconds / 60).toFixed(1)}m` : '-'}
                      </td>
                      <td className="px-6 py-3">
                        <button
                          onClick={() => setSelectedJob(job)}
                          className="text-blue-600 hover:text-blue-700 font-medium text-xs"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminDashboard;
