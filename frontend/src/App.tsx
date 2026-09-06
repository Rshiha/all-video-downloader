import React, { useState, useEffect, useRef } from "react";
import { Download, Film, Music, AlertCircle, CheckCircle2, Loader2, Sparkles, X, ShieldAlert } from "lucide-react";

type JobStatus = "queued" | "downloading" | "converting" | "done" | "error";

interface Job {
  id: string;
  status: JobStatus;
  progress: number;
  error?: string;
  title?: string;
  format?: string;
  quality?: string;
  has_file?: boolean;
  is_playlist?: boolean;
  playlist_index?: number;
  playlist_count?: number;
  current_video_title?: string;
}

interface ProbeData {
  title: string;
  duration: number;
  thumbnail: string;
  channel: string;
  qualities: number[];
  is_too_long: boolean;
  is_playlist?: boolean;
  playlist_count?: number;
}

export default function App() {
  const [url, setUrl] = useState("");
  const [format, setFormat] = useState<"mp4" | "mp3">("mp4");
  const [quality, setQuality] = useState("720");
  const [bitrate, setBitrate] = useState("192");
  
  const [probeData, setProbeData] = useState<ProbeData | null>(null);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);

  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [submitting, setSubmitting] = useState(false);
  const pollTimers = useRef<Record<string, number>>({});

  // Auto-probe metadata when URL changes and looks like YouTube
  useEffect(() => {
    const trimmed = url.trim();
    if (trimmed.includes("youtube.com") || trimmed.includes("youtu.be")) {
      const handler = setTimeout(() => {
        handleProbe(trimmed);
      }, 600);
      return () => clearTimeout(handler);
    } else {
      setProbeData(null);
      setProbeError(null);
    }
  }, [url]);

  async function handleProbe(targetUrl: string) {
    setProbing(true);
    setProbeError(null);
    try {
      const res = await fetch("/api/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: targetUrl }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to fetch video details");
      }
      setProbeData(data);
    } catch (err: any) {
      setProbeError(err.message || "Invalid or unsupported YouTube URL");
      setProbeData(null);
    } finally {
      setProbing(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;

    setSubmitting(true);
    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), format, quality, bitrate }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to start download job");
      }

      const jobId = data.job_id;
      setJobs((prev) => ({
        ...prev,
        [jobId]: {
          id: jobId,
          status: "queued",
          progress: 0,
          title: probeData?.title || "Processing...",
          format,
          quality: format === "mp4" ? `${quality}p` : `${bitrate}kbps`,
        },
      }));

      startPolling(jobId);
    } catch (err: any) {
      alert(err.message || "An error occurred");
    } finally {
      setSubmitting(false);
    }
  }

  function startPolling(id: string) {
    if (pollTimers.current[id]) clearTimeout(pollTimers.current[id]);

    const tick = async () => {
      try {
        const res = await fetch(`/api/jobs/${id}`);
        if (!res.ok) return;
        const data: Job = await res.json();

        setJobs((prev) => ({
          ...prev,
          [id]: {
            ...prev[id],
            ...data,
          },
        }));

        if (data.status !== "done" && data.status !== "error") {
          pollTimers.current[id] = window.setTimeout(tick, 1500);
        }
      } catch (err) {
        // Retry polling on temporary network failure
        pollTimers.current[id] = window.setTimeout(tick, 2500);
      }
    };

    tick();
  }

  function removeJob(id: string) {
    if (pollTimers.current[id]) {
      clearTimeout(pollTimers.current[id]);
      delete pollTimers.current[id];
    }
    setJobs((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }

  function formatDuration(seconds: number) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col justify-between py-12 px-4 selection:bg-emerald-500 selection:text-neutral-950">
      <div className="w-full max-w-xl mx-auto space-y-8">
        
        {/* Header */}
        <header className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-neutral-900 border border-neutral-800 text-xs font-medium text-emerald-400">
            <Sparkles className="w-3.5 h-3.5" /> Fast & Lightweight Media Service
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-white">Media Downloader</h1>
          <p className="text-sm text-neutral-400">
            Fast, lightweight YouTube to MP4 / MP3 converter service
          </p>
        </header>

        {/* Input & Form */}
        <form onSubmit={submit} className="bg-neutral-900 rounded-2xl p-6 border border-neutral-800 shadow-xl space-y-5">
          <div className="space-y-2">
            <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-400">
              YouTube Video URL
            </label>
            <div className="relative">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                required
                className="w-full rounded-xl bg-neutral-950 border border-neutral-800 px-4 py-3.5 text-sm placeholder-neutral-500 text-neutral-100 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all pr-10"
              />
              {probing && (
                <div className="absolute right-3 top-3.5 text-neutral-400">
                  <Loader2 className="w-5 h-5 animate-spin" />
                </div>
              )}
            </div>

            {probeError && (
              <p className="text-xs text-red-400 flex items-center gap-1.5 pt-1">
                <AlertCircle className="w-3.5 h-3.5" /> {probeError}
              </p>
            )}
          </div>

          {/* Video Metadata Preview Card */}
          {probeData && (
            <div className="bg-neutral-950/80 rounded-xl p-4 border border-neutral-800/80 flex gap-4 items-center">
              {probeData.thumbnail ? (
                <img
                  src={probeData.thumbnail}
                  alt={probeData.title}
                  className="w-24 h-16 object-cover rounded-lg border border-neutral-800 flex-shrink-0"
                />
              ) : (
                <div className="w-24 h-16 bg-neutral-900 rounded-lg flex items-center justify-center border border-neutral-800 flex-shrink-0">
                  <Film className="w-6 h-6 text-neutral-600" />
                </div>
              )}
              <div className="min-w-0 flex-1 space-y-1">
                <h3 className="text-xs font-semibold text-neutral-200 line-clamp-1">
                  {probeData.title}
                </h3>
                <p className="text-xs text-neutral-400 flex items-center gap-1.5">
                  <span>{probeData.channel}</span>
                  <span>•</span>
                  <span>{probeData.is_playlist ? `Playlist (${probeData.playlist_count} videos)` : formatDuration(probeData.duration)}</span>
                </p>
                {probeData.is_too_long && (
                  <p className="text-[11px] text-amber-400 flex items-center gap-1">
                    <ShieldAlert className="w-3 h-3" /> Exceeds 30 min limit
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Format & Quality Settings */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-neutral-400">Format</label>
              <div className="grid grid-cols-2 gap-1 bg-neutral-950 p-1 rounded-xl border border-neutral-800">
                <button
                  type="button"
                  onClick={() => setFormat("mp4")}
                  className={`flex items-center justify-center gap-1.5 py-2 text-xs font-medium rounded-lg transition-all ${
                    format === "mp4"
                      ? "bg-neutral-800 text-emerald-400 shadow-sm"
                      : "text-neutral-400 hover:text-neutral-200"
                  }`}
                >
                  <Film className="w-3.5 h-3.5" /> MP4
                </button>
                <button
                  type="button"
                  onClick={() => setFormat("mp3")}
                  className={`flex items-center justify-center gap-1.5 py-2 text-xs font-medium rounded-lg transition-all ${
                    format === "mp3"
                      ? "bg-neutral-800 text-emerald-400 shadow-sm"
                      : "text-neutral-400 hover:text-neutral-200"
                  }`}
                >
                  <Music className="w-3.5 h-3.5" /> MP3
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-neutral-400">
                {format === "mp4" ? "Video Resolution" : "Audio Bitrate"}
              </label>
              {format === "mp4" ? (
                <select
                  value={quality}
                  onChange={(e) => setQuality(e.target.value)}
                  className="w-full rounded-xl bg-neutral-950 border border-neutral-800 px-3 py-2.5 text-xs text-neutral-200 focus:outline-none focus:border-emerald-500"
                >
                  <option value="2160">2160p (4K Ultra HD)</option>
                  <option value="1440">1440p (2K Quad HD)</option>
                  <option value="1080">1080p (Full HD)</option>
                  <option value="720">720p (HD)</option>
                  <option value="480">480p (SD)</option>
                  <option value="360">360p (Low)</option>
                </select>
              ) : (
                <select
                  value={bitrate}
                  onChange={(e) => setBitrate(e.target.value)}
                  className="w-full rounded-xl bg-neutral-950 border border-neutral-800 px-3 py-2.5 text-xs text-neutral-200 focus:outline-none focus:border-emerald-500"
                >
                  <option value="320">320 kbps (Best)</option>
                  <option value="256">256 kbps (High)</option>
                  <option value="192">192 kbps (Standard)</option>
                  <option value="128">128 kbps (Compact)</option>
                </select>
              )}
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting || (probeData?.is_too_long ?? false)}
            className="w-full rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:hover:bg-emerald-500 text-neutral-950 font-semibold py-3.5 text-sm transition-colors flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/10 cursor-pointer"
          >
            {submitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> Creating job...
              </>
            ) : (
              <>
                <Download className="w-4 h-4" /> Start Download
              </>
            )}
          </button>
        </form>

        {/* Active & Completed Jobs Section */}
        {Object.keys(jobs).length > 0 && (
          <section className="space-y-4">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 px-1">
              Active Downloads ({Object.keys(jobs).length})
            </h2>

            <div className="space-y-3">
              {Object.values(jobs).map((job) => (
                <div
                  key={job.id}
                  className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 shadow-md space-y-3 relative group"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1 min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-neutral-200 truncate">
                          {job.title || `Job ${job.id.slice(0, 8)}`}
                        </span>
                        <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400">
                          {job.format} • {job.quality}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 text-xs">
                        {job.status === "queued" && (
                          <span className="text-neutral-400 flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-neutral-400 animate-pulse" /> Queued
                          </span>
                        )}
                        {job.status === "downloading" && (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <Loader2 className="w-3 h-3 animate-spin" /> Downloading
                          </span>
                        )}
                        {job.status === "converting" && (
                          <span className="text-amber-400 flex items-center gap-1">
                            <Loader2 className="w-3 h-3 animate-spin" /> Processing FFmpeg...
                          </span>
                        )}
                        {job.status === "done" && (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> Ready
                          </span>
                        )}
                        {job.status === "error" && (
                          <span className="text-red-400 flex items-center gap-1">
                            <AlertCircle className="w-3 h-3" /> Failed
                          </span>
                        )}
                      </div>
                    </div>

                    <button
                      onClick={() => removeJob(job.id)}
                      className="text-neutral-500 hover:text-neutral-300 p-1 rounded-lg hover:bg-neutral-800 transition-colors"
                      title="Clear job"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Progress Bar */}
                  {(job.status === "downloading" || job.status === "converting" || job.status === "queued") && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-[11px] text-neutral-400">
                        <span>{job.status === "converting" ? "Extracting audio" : "Downloading video"}</span>
                        <span>{job.progress}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-neutral-950 overflow-hidden p-0.5 border border-neutral-800">
                        <div
                          className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Download Link */}
                  {job.status === "done" && (
                    <div className="pt-1 flex items-center justify-between">
                      <a
                        href={`/api/jobs/${job.id}/file`}
                        download
                        className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400 hover:text-emerald-300 hover:underline"
                      >
                        <Download className="w-3.5 h-3.5" /> Download File →
                      </a>
                      <span className="text-[10px] text-neutral-500">Auto-deletes after download</span>
                    </div>
                  )}

                  {/* Error Message */}
                  {job.status === "error" && (
                    <div className="bg-red-950/30 border border-red-900/50 rounded-lg p-2.5 text-xs text-red-400">
                      {job.error || "An unknown error occurred during download."}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

      </div>

      {/* Educational Purpose Disclaimer Footer */}
      <footer className="mt-12 text-center text-xs text-neutral-500 space-y-1">
        <p>Educational purpose only. Please respect copyright laws and content creators' rights.</p>
      </footer>
    </div>
  );
}
