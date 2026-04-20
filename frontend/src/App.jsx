import React, { useState } from "react";
import { Search, Github, Loader2, Download, AlertCircle, 
         GitMerge, FileCode, Layers, BarChart2, ChevronRight } from "lucide-react";
import RadarChartComponent from "./components/RadarChartComponent";
import jsPDF from "jspdf";
import html2canvas from "html2canvas";
import "./index.css";

/* ── Helpers ── */
const scoreColor = (v) =>
  v >= 80 ? "#00e676" : v >= 60 ? "#ffab40" : "#ff5252";

const scoreLabel = (v) =>
  v >= 80 ? "Excellent" : v >= 60 ? "Adequate" : "Needs Work";

const criteriaDesc = {
  maintainability: "Variable naming, modularity & nesting depth",
  framework_skill: "Async patterns, REST principles & stdlib usage",
  error_handling:  "try/except coverage, logging & failure modes",
  algorithmic_efficiency: "Data structures, complexity & hot-path design",
};

/* ── Sub-components ── */
function TopBar() {
  return (
    <header style={{ borderBottom: "1px solid var(--border)" }}
      className="flex items-center justify-between px-8 py-4">
      <div className="flex items-center gap-3">
        <div style={{ background: "var(--cyan)", borderRadius: 6, padding: "5px 7px" }}>
          <Github size={16} color="#080d14" strokeWidth={2.5} />
        </div>
        <span className="font-display font-700 text-sm tracking-widest uppercase"
          style={{ color: "var(--text-primary)", letterSpacing: "0.14em" }}>
          DevLens
        </span>
        <span style={{ color: "var(--border-bright)", marginInline: 4 }}>·</span>
        <span className="metric-label">Candidate Intelligence</span>
      </div>
      <div className="status-badge">
        <span className="status-dot" />
        System Online
      </div>
    </header>
  );
}

function StatPill({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-3 panel-2 px-4 py-3"
      style={{ borderRadius: 8, minWidth: 140 }}>
      <Icon size={14} style={{ color: "var(--cyan)" }} />
      <div>
        <div className="metric-label" style={{ fontSize: "0.62rem" }}>{label}</div>
        <div className="font-mono" style={{ color: "var(--text-primary)", fontSize: "0.82rem", fontWeight: 500 }}>
          {value}
        </div>
      </div>
    </div>
  );
}

function ScoreRow({ dim, val, rationale, index }) {
  const color = scoreColor(val);
  const label = scoreLabel(val);
  const desc  = criteriaDesc[dim] ?? "";
  const key   = dim.replace(/_/g, " ");
 
  return (
    <div className="animate-fadeInUp" style={{ animationDelay: `${index * 0.08}s`, opacity: 0 }}>
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="font-display font-600 capitalize"
            style={{ fontSize: "0.9rem", color: "var(--text-primary)" }}>
            {key}
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: 2 }}>
            {desc}
          </div>
        </div>
        <div className="text-right ml-4">
          <div className="font-mono font-500" style={{ fontSize: "1.4rem", color, lineHeight: 1 }}>
            {val}
          </div>
          <div style={{ fontSize: "0.65rem", color, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            {label}
          </div>
        </div>
      </div>
      <div className="score-bar-track" style={{ marginBottom: rationale ? 8 : 0 }}>
        <div className="score-bar-fill" style={{ width: `${val}%`, background: color }} />
      </div>
      {rationale && (
        <div style={{
          fontSize: "0.72rem",
          color: "var(--text-secondary)",
          fontFamily: "JetBrains Mono",
          lineHeight: 1.6,
          paddingLeft: 2,
          borderLeft: `2px solid ${color}33`,
          paddingLeft: 8,
          marginTop: 4,
        }}>
          {rationale}
        </div>
      )}
    </div>
  );
}

function PipelineStat({ icon: Icon, label, value, delay }) {
  return (
    <div className="flex flex-col items-center gap-2 animate-fadeInUp" style={{ animationDelay: delay, opacity: 0 }}>
      <div style={{
        width: 40, height: 40, borderRadius: 10,
        background: "var(--cyan-dim)",
        border: "1px solid rgba(0,212,255,0.2)",
        display: "flex", alignItems: "center", justifyContent: "center"
      }}>
        <Icon size={16} style={{ color: "var(--cyan)" }} />
      </div>
      <div className="font-mono font-500" style={{ fontSize: "1.3rem", color: "var(--cyan)" }}>
        {value}
      </div>
      <div className="metric-label" style={{ fontSize: "0.62rem", textAlign: "center" }}>
        {label}
      </div>
    </div>
  );
}

/* ── Main App ── */
export default function App() {
  const [input,   setInput]   = useState("");
  const [loading, setLoading] = useState(false);
  const [report,  setReport]  = useState(null);
  const [error,   setError]   = useState(null);

  /* parse summary numbers */
  const parseSummary = (summary = "") => {
    const repos = summary.match(/(\d+) original/)?.[1]  ?? "—";
    const diffs = summary.match(/(\d+) diff/)?.[1]      ?? "—";
    const pruned= summary.match(/pruned to (\d+)/)?.[1] ?? "—";
    const chunks= summary.match(/(\d+) clean/)?.[1]     ?? "—";
    return { repos, diffs, pruned, chunks };
  };

  const handleAnalyze = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res  = await fetch("http://localhost:8000/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_id: input }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Analysis failed.");
      setReport(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPDF = async () => {
    const el = document.getElementById("report-section");
    const canvas = await html2canvas(el, { backgroundColor: "#080d14", scale: 2 });
    const img = canvas.toDataURL("image/png");
    const pdf = new jsPDF({ orientation: "portrait", unit: "px", format: "a4" });
    const w = pdf.internal.pageSize.getWidth();
    const h = (canvas.height * w) / canvas.width;
    pdf.addImage(img, "PNG", 0, 0, w, h);
    pdf.save(`${report.candidate}-devlens-report.pdf`);
  };

  const numScores = report
    ? Object.values(report.scores).filter(v => typeof v === "number")
    : [];
  const avgScore = numScores.length
    ? Math.round(numScores.reduce((a, b) => a + b, 0) / numScores.length)
    : null;

  const stats = report ? parseSummary(report.summary) : null;

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <TopBar />

      <main style={{ flex: 1, maxWidth: 1100, margin: "0 auto", width: "100%", padding: "48px 24px" }}>

        {/* ── HERO ── */}
        <div className="animate-fadeInUp" style={{ marginBottom: 48, opacity: 0 }}>
          <div className="metric-label" style={{ marginBottom: 12, color: "var(--cyan)" }}>
            ◈ &nbsp;AI-Powered Pipeline · 5 Phases
          </div>
          <h1 className="font-display"
            style={{ fontSize: "clamp(2rem, 4vw, 3rem)", fontWeight: 800,
                     color: "var(--text-primary)", lineHeight: 1.1, marginBottom: 12 }}>
            GitHub Candidate
            <br />
            <span style={{ color: "var(--cyan)" }}>Intelligence Report</span>
          </h1>
          <p style={{ color: "var(--text-secondary)", maxWidth: 480, lineHeight: 1.7, fontSize: "0.95rem" }}>
            Enter a GitHub username to run AST-based code analysis through a 5-phase RAG pipeline,
            scored against an engineering rubric by a local LLM.
          </p>
        </div>

        {/* ── SEARCH ── */}
        <div className="panel glow-cyan animate-fadeInUp delay-2"
          style={{ padding: 24, marginBottom: 32 }}>
          <form onSubmit={handleAnalyze} style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <div style={{ position: "relative", flex: 1 }}>
              <Github size={15} style={{
                position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)",
                color: "var(--text-muted)"
              }} />
              <input
                type="text"
                placeholder="github.com/username  or  username"
                className="search-input"
                style={{ paddingLeft: 40 }}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                required
              />
            </div>
            <button type="submit" disabled={loading} className="btn-analyze">
              {loading
                ? <Loader2 size={15} className="animate-spin" />
                : <Search size={15} />}
              {loading ? "Analyzing..." : "Analyze"}
            </button>
          </form>

          {/* pipeline phase strip */}
          <div style={{ marginTop: 18, display: "flex", gap: 6, alignItems: "center" }}>
            {["Ingest", "Prune", "Assemble", "Evaluate", "Report"].map((phase, i) => (
              <React.Fragment key={phase}>
                <span className="metric-label" style={{
                  fontSize: "0.65rem",
                  color: loading ? "var(--cyan)" : "var(--text-muted)",
                  transition: "color 0.3s",
                  transitionDelay: `${i * 0.15}s`
                }}>
                  {phase}
                </span>
                {i < 4 && <ChevronRight size={10} style={{ color: "var(--text-muted)", flexShrink: 0 }} />}
              </React.Fragment>
            ))}
          </div>
        </div>

        {/* ── ERROR ── */}
        {error && (
          <div className="panel animate-fadeInUp" style={{
            padding: "16px 20px", marginBottom: 24,
            borderColor: "rgba(255,82,82,0.4)",
            background: "rgba(255,82,82,0.05)",
            display: "flex", alignItems: "center", gap: 12
          }}>
            <AlertCircle size={16} style={{ color: "#ff5252", flexShrink: 0 }} />
            <span style={{ color: "#ff5252", fontSize: "0.88rem", fontFamily: "'JetBrains Mono'" }}>
              {error}
            </span>
          </div>
        )}

        {/* ── REPORT ── */}
        {report && (
          <div id="report-section" className="animate-fadeInUp" style={{ opacity: 0 }}>

            {/* Header row */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
              <div>
                <div className="metric-label" style={{ marginBottom: 6 }}>Candidate Profile</div>
                <div className="font-display" style={{ fontSize: "1.8rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  @{report.candidate}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {avgScore !== null && (
                  <div style={{ textAlign: "right" }}>
                    <div className="metric-label" style={{ fontSize: "0.62rem", marginBottom: 2 }}>Overall Score</div>
                    <div className="font-mono" style={{
                      fontSize: "2.2rem", fontWeight: 600, lineHeight: 1,
                      color: scoreColor(avgScore)
                    }}>
                      {avgScore}<span style={{ fontSize: "1rem", color: "var(--text-muted)" }}>/100</span>
                    </div>
                  </div>
                )}
                <button onClick={handleDownloadPDF} className="btn-pdf">
                  <Download size={13} />
                  PDF Report
                </button>
              </div>
            </div>

            {/* Pipeline stats */}
            {stats && (
              <div className="panel" style={{ padding: "20px 24px", marginBottom: 24 }}>
                <div className="metric-label" style={{ marginBottom: 16, fontSize: "0.65rem" }}>
                  Pipeline Execution Summary
                </div>
                <div style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
                  <PipelineStat icon={Github}    label="Repos Scanned" value={stats.repos}  delay="0.05s" />
                  <PipelineStat icon={GitMerge}  label="Diffs Ingested" value={stats.diffs}  delay="0.1s"  />
                  <PipelineStat icon={FileCode}  label="After Prune"   value={stats.pruned} delay="0.15s" />
                  <PipelineStat icon={Layers}    label="Code Chunks"   value={stats.chunks} delay="0.2s"  />
                  <PipelineStat icon={BarChart2} label="Avg Score"     value={avgScore ?? "—"} delay="0.25s" />
                </div>
              </div>
            )}

            {/* Scores + Radar */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>

              {/* Score dimensions */}
              <div className="panel" style={{ padding: 24 }}>
                <div className="metric-label" style={{ marginBottom: 20, fontSize: "0.65rem" }}>
                  Dimension Scores
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
                  {Object.entries(report.scores)
                    .filter(([, v]) => typeof v === "number")
                    .map(([dim, val], i) => (
                      <ScoreRow key={dim} dim={dim} val={val} rationale={report.scores.rationale?.[dim]} index={i} />
                    ))}
                </div>
                  
                {report.scores.note && (
                  <div style={{
                    marginTop: 20, padding: "10px 14px",
                    background: "rgba(255,171,64,0.07)",
                    border: "1px solid rgba(255,171,64,0.2)",
                    borderRadius: 7
                  }}>
                    <div className="font-mono" style={{ fontSize: "0.7rem", color: "#ffab40", lineHeight: 1.6 }}>
                      ⚠ &nbsp;{report.scores.note}
                    </div>
                  </div>
                )}
              </div>

              {/* Radar chart */}
              <div className="panel" style={{ padding: 24, display: "flex", flexDirection: "column" }}>
                <div className="metric-label" style={{ marginBottom: 16, fontSize: "0.65rem" }}>
                  Competency Radar
                </div>
                <div style={{ flex: 1, minHeight: 280 }}>
                  <RadarChartComponent data={report.scores} />
                </div>
                <div className="divider" style={{ margin: "16px 0" }} />
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  {[["≥80", "Excellent", "#00e676"], ["60–79", "Adequate", "#ffab40"], ["<60", "Needs Work", "#ff5252"]].map(([range, lbl, color]) => (
                    <div key={lbl} className="flex items-center gap-2">
                      <div style={{ width: 8, height: 8, borderRadius: 2, background: color }} />
                      <span style={{ fontSize: "0.68rem", color: "var(--text-secondary)", fontFamily: "JetBrains Mono" }}>
                        {range} · {lbl}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Rubric note */}
            <div style={{
              marginTop: 16, padding: "14px 18px",
              background: "var(--panel-2)",
              border: "1px solid var(--border)",
              borderRadius: 8, display: "flex", alignItems: "center", gap: 10
            }}>
              <FileCode size={13} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
              <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontFamily: "JetBrains Mono" }}>
                Scored against <span style={{ color: "var(--cyan)" }}>rubric.json</span> · Role: Backend Engineer ·
                Model: llama3.2 · Top-K: 15 chunks
              </span>
            </div>

          </div>
        )}

      </main>

      {/* Footer */}
      <footer style={{ borderTop: "1px solid var(--border)", padding: "16px 32px",
        display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="metric-label" style={{ fontSize: "0.65rem" }}>DevLens v1.0 · GitHub Intelligence Platform</span>
        <span className="metric-label" style={{ fontSize: "0.65rem" }}>Powered by Tree-sitter · Ollama · FastAPI</span>
      </footer>
    </div>
  );
}