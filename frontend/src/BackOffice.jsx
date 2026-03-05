import { useState, useEffect, useCallback } from "react";

// ── CONFIG ────────────────────────────────────────────────────────────────────
const API = "http://localhost:8000";
const POLL_MS = 8000; // refresh case feed every 8s

// ── TOKENS ────────────────────────────────────────────────────────────────────
const T = {
  void:       "#0A0A0A",
  dark:       "#111111",
  darkMid:    "#181818",
  darkBorder: "#1E1E1E",
  page:       "#F5F5F5",
  paper:      "#FFFFFF",
  paperDark:  "#EBEBEB",
  ink:        "#1A1A1A",
  ink2:       "#3A3A3A",
  ink3:       "#666666",
  ink4:       "#999999",
  border:     "#DCDCDC",
  borderMid:  "#C0C0C0",
  red:        "#C8371A",
  redBg:      "#FEF1EE",
  redBorder:  "#F0C4BA",
  white:      "#FFFFFF",
};

// ── SHARED COMPONENTS ─────────────────────────────────────────────────────────
function FL({ children }) {
  return (
    <div style={{ fontSize:8, fontWeight:800, color:T.ink4, letterSpacing:1.4, marginBottom:4, textTransform:"uppercase", fontFamily:"monospace" }}>
      {children}
    </div>
  );
}

function Tag({ children, alert, dim }) {
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", padding:"2px 7px", borderRadius:2,
      fontSize:9, fontWeight:800, letterSpacing:1.1, fontFamily:"monospace",
      color:      alert ? T.red  : dim ? T.ink4 : T.ink3,
      background: alert ? T.redBg : T.paper,
      border:     `1px solid ${alert ? T.redBorder : T.border}`,
    }}>{children}</span>
  );
}

function Rule({ label }) {
  return (
    <div style={{ display:"flex", alignItems:"center", gap:12, margin:"18px 0 12px" }}>
      <div style={{ flex:1, height:1, background:T.border }}/>
      <span style={{ fontSize:9, fontWeight:800, color:T.ink4, letterSpacing:1.8, textTransform:"uppercase", fontFamily:"monospace", whiteSpace:"nowrap" }}>{label}</span>
      <div style={{ flex:1, height:1, background:T.border }}/>
    </div>
  );
}

function ErrBox({ msg }) {
  return <div style={{ background:T.redBg, border:`1px solid ${T.redBorder}`, borderRadius:5, padding:"10px 14px", fontSize:12, color:T.red, marginBottom:14, fontWeight:600 }}>{msg}</div>;
}

function timeAgo(iso) {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 3600)  return `${Math.floor(s/60)}m ago`;
  if (s < 86400) return `${Math.floor(s/3600)}h ago`;
  return `${Math.floor(s/86400)}d ago`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-AU", { hour:"2-digit", minute:"2-digit", hour12:false });
}

// ── SIDEBAR ───────────────────────────────────────────────────────────────────
function Sidebar({ active, onNav, pendingCount }) {
  return (
    <div style={{ width:190, flexShrink:0, background:T.dark, borderRight:`1px solid ${T.darkBorder}`, display:"flex", flexDirection:"column" }}>
      <div style={{ padding:"14px 16px 12px", borderBottom:`1px solid ${T.darkBorder}` }}>
        <div style={{ fontSize:10, fontWeight:900, color:T.white, letterSpacing:3.5, fontFamily:"monospace" }}>CUMMINS</div>
        <div style={{ fontSize:8, color:"#888888", letterSpacing:2, fontFamily:"monospace", marginTop:1 }}>BACK OFFICE</div>
      </div>
      <div style={{ flex:1, paddingTop:8 }}>
        {[
          { id:"cases",  label:"CASE FEED",    badge: pendingCount > 0 ? pendingCount : null },
          { id:"assign", label:"ASSIGN TICKET", accent:true },
        ].map(item => {
          const a = active === item.id;
          return (
            <button key={item.id} onClick={() => onNav(item.id)} style={{
              width:"100%", display:"flex", alignItems:"center", justifyContent:"space-between",
              padding:"10px 16px", background:a?"#1a1a1a":"none",
              border:"none", borderLeft:`3px solid ${a ? T.red : "transparent"}`, cursor:"pointer",
            }}>
              <span style={{ fontSize:10, fontWeight:800, letterSpacing:0.8, fontFamily:"monospace", color:a?T.white:"#AAAAAA" }}>{item.label}</span>
              {item.badge != null && <span style={{ width:18, height:18, borderRadius:9, background:T.red, color:T.white, fontSize:9, fontWeight:800, display:"flex", alignItems:"center", justifyContent:"center" }}>{item.badge}</span>}
              {item.accent && !a && <span style={{ fontSize:8, color:T.red, fontFamily:"monospace" }}>◆</span>}
            </button>
          );
        })}
      </div>
      <div style={{ padding:"10px 16px", borderTop:`1px solid ${T.darkBorder}` }}>
        <div style={{ fontSize:8, color:"#666666", fontFamily:"monospace", letterSpacing:1 }}>LIVE DATA · v0.4</div>
      </div>
    </div>
  );
}

// ── CASE FEED ─────────────────────────────────────────────────────────────────
// Shows tickets needing back-office action:
//   escalation != null             → escalation review
//   approval_request.status=pending → resolution approval
function CaseFeed({ tickets, loading, activeId, onSelect }) {
  const [filter, setFilter] = useState("all");

  const cases = tickets.map(t => ({
    ...t,
    _type: t.escalation ? "escalation" : "resolution",
  }));

  const shown = filter === "all" ? cases : cases.filter(c => c._type === filter);

  return (
    <div style={{ width:268, flexShrink:0, borderRight:`1px solid ${T.border}`, background:T.paper, display:"flex", flexDirection:"column" }}>
      <div style={{ padding:"12px 14px 10px", borderBottom:`1px solid ${T.border}` }}>
        <div style={{ fontSize:8, fontWeight:800, color:T.ink4, letterSpacing:2, marginBottom:8, fontFamily:"monospace" }}>CASE FEED</div>
        <div style={{ display:"flex", gap:3 }}>
          {[["all","ALL"],["escalation","ESC"],["resolution","RES"]].map(([id,lab]) => (
            <button key={id} onClick={() => setFilter(id)} style={{
              flex:1, padding:"4px 0", borderRadius:2, fontSize:9, fontWeight:800,
              cursor:"pointer", border:"none", fontFamily:"monospace",
              background:filter===id?T.dark:T.paperDark, color:filter===id?T.white:T.ink4,
            }}>{lab}</button>
          ))}
        </div>
      </div>

      <div style={{ flex:1, overflowY:"auto" }}>
        {loading && shown.length === 0 && (
          <div style={{ padding:20, fontSize:11, color:T.ink4, textAlign:"center" }}>Loading tickets…</div>
        )}
        {!loading && shown.length === 0 && (
          <div style={{ padding:20, fontSize:11, color:T.ink4, textAlign:"center" }}>No {filter !== "all" ? filter : ""} cases pending</div>
        )}
        {shown.map(c => {
          const isActive = c.ticket.ticket_id === activeId;
          const isEsc    = c._type === "escalation";
          const fcs      = c.ticket.fault_codes || [];
          const escType  = c.escalation?.escalation_type;
          return (
            <div key={c.ticket.ticket_id} onClick={() => onSelect(c)} style={{
              padding:"12px 14px", borderBottom:`1px solid ${T.border}`,
              borderLeft:`3px solid ${isActive ? T.red : "transparent"}`,
              background:isActive?T.paperDark:"transparent", cursor:"pointer",
            }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6 }}>
                <div style={{ display:"flex", gap:5, alignItems:"center" }}>
                  <span style={{ fontSize:8, fontWeight:800, letterSpacing:1, fontFamily:"monospace", color:isEsc?T.red:T.ink3, border:`1px solid ${isEsc?T.red+"33":T.border}`, padding:"1px 6px", borderRadius:2 }}>
                    {isEsc
                      ? escType==="unsafe" ? "⚠ UNSAFE" : escType==="technical_support" ? "TECH ESC" : "WARRANTY"
                      : "RESOLUTION"}
                  </span>
                  <span style={{ width:5, height:5, borderRadius:"50%", background:T.red, display:"inline-block", opacity:0.8 }}/>
                </div>
                <span style={{ fontSize:9, color:T.ink4, fontFamily:"monospace" }}>{timeAgo(c.ticket.escalated_at || c.ticket.created_at)}</span>
              </div>
              <div style={{ fontSize:13, fontWeight:700, color:T.ink, marginBottom:2 }}>{c.ticket.customer}</div>
              <div style={{ fontSize:10, color:T.ink4, marginBottom:7 }}>{c.ticket.location}</div>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                <div style={{ display:"flex", gap:4 }}>
                  {fcs.slice(0,3).map(fc => (
                    <span key={fc} style={{ fontSize:9, fontWeight:700, background:T.dark, color:"#505050", borderRadius:2, padding:"1px 6px", fontFamily:"monospace" }}>{fc}</span>
                  ))}
                  {fcs.length > 3 && <span style={{ fontSize:9, color:T.ink4 }}>+{fcs.length-3}</span>}
                </div>
                <span style={{ fontSize:9, color:T.ink4, fontFamily:"monospace" }}>{c.ticket.ticket_id}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── CASE FILE ─────────────────────────────────────────────────────────────────
function CaseFile({ caseData, onRefresh }) {
  const [note, setNote]         = useState("");
  const [saving, setSaving]     = useState(false);
  const [saveErr, setSaveErr]   = useState("");
  const [saveDone, setSaveDone] = useState(false);
  const [aiView, setAiView]     = useState("summary");

  const ticket  = caseData.ticket           || {};
  const triage  = caseData.triage           || {};
  const esc     = caseData.escalation       || null;
  const apr     = caseData.approval_request || null;
  const rca     = caseData.rca              || null;
  const rcaSkip = caseData.rca_skip         || null;
  const isEsc   = !!esc;
  const isClosed = ticket.status === "resolved" || saveDone;

  const reviewApproval = async (status) => {
    if (status === "rejected" && !note.trim()) {
      setSaveErr("A reviewer comment is required when rejecting."); return;
    }
    setSaveErr(""); setSaving(true);
    try {
      const params = new URLSearchParams({ status });
      if (note.trim()) params.set("reviewer_comment", note.trim());
      const r = await fetch(`${API}/api/approve/${ticket.ticket_id}?${params}`, { method:"PATCH" });
      const d = await r.json();
      if (!d.success) throw new Error(d.detail || "Request failed");
      setSaveDone(true);
      onRefresh();
    } catch (e) {
      setSaveErr(e.message || "Failed");
    }
    setSaving(false);
  };

  const RCA_ICONS = {
    confirmed:{ s:"✓", c:T.ink  },
    ruled_out:{ s:"—", c:T.ink4 },
    blocked:  { s:"⊘", c:T.red  },
    escalated:{ s:"↑", c:T.ink2 },
  };

  // Normalise triage shape — backend may nest under triage_results
  const sev    = triage?.severity         || triage?.triage_results?.severity         || {};
  const diag   = triage?.diagnosis        || triage?.triage_results?.diagnosis        || {};
  const safety = triage?.safety           || triage?.triage_results?.safety           || {};
  const parts  = triage?.resources?.parts || triage?.triage_results?.resources?.parts || [];

  return (
    <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden", background:T.page }}>

      {/* ── HEADER ── */}
      <div style={{ background:T.void, padding:"13px 22px 14px", flexShrink:0, borderBottom:`1px solid ${T.darkBorder}` }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:8 }}>
          <div style={{ display:"flex", gap:8, alignItems:"center" }}>
            <span style={{ fontSize:9, color:"#2E2E2E", fontFamily:"monospace", letterSpacing:1.5 }}>{ticket.ticket_id}</span>
            <span style={{ width:1, height:10, background:"#222" }}/>
            <span style={{ fontSize:9, fontWeight:800, letterSpacing:1.2, fontFamily:"monospace", color:isEsc?T.red:"#555" }}>
              {isEsc
                ? esc.escalation_type==="unsafe"            ? "⚠ UNSAFE ESCALATION"
                : esc.escalation_type==="technical_support" ? "TECH SUPPORT ESCALATION"
                : "PARTS / WARRANTY ESCALATION"
                : "RESOLUTION REPORT"}
            </span>
            {isClosed && <span style={{ fontSize:9, fontWeight:800, color:"#444", fontFamily:"monospace" }}>· CLOSED</span>}
          </div>
          <div style={{ textAlign:"right" }}>
            <div style={{ fontSize:9, color:"#333", fontFamily:"monospace" }}>{ticket.tech_id}</div>
            <div style={{ fontSize:9, color:"#2A2A2A", fontFamily:"monospace", marginTop:2 }}>{fmtTime(ticket.created_at)}</div>
          </div>
        </div>
        <div style={{ fontSize:19, fontWeight:800, color:T.white, marginBottom:3, letterSpacing:-0.3 }}>{ticket.customer}</div>
        <div style={{ fontSize:11, color:"#3A3A3A", marginBottom:11 }}>{ticket.location} · {ticket.equipment_model || ticket.serial_number}</div>
        <div style={{ display:"flex", gap:6, flexWrap:"wrap" }}>
          {(ticket.fault_codes || []).map(fc => (
            <span key={fc} style={{ fontSize:10, fontWeight:700, background:"#161616", color:"#565656", borderRadius:2, padding:"3px 9px", fontFamily:"monospace", border:"1px solid #1E1E1E" }}>{fc}</span>
          ))}
        </div>
      </div>

      {/* ── SCROLLABLE BODY ── */}
      <div style={{ flex:1, overflowY:"auto", padding:"18px 22px 40px" }}>

        {/* TECH SUBMISSION */}
        <div style={{ background:T.paper, borderRadius:6, padding:"15px 18px", marginBottom:10, border:`1px solid ${T.border}` }}>
          <FL>Technician Submission</FL>

          {isEsc ? (
            <>
              <div style={{ fontSize:12, color:T.ink2, lineHeight:1.8, marginBottom:12 }}>
                {esc.escalation_reason?.reason || "No reason provided"}
              </div>
              {esc.who_and_where && (
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:12, marginBottom:12 }}>
                  <div><FL>Time on Site</FL><div style={{ fontSize:11, color:T.ink, fontWeight:600 }}>{esc.who_and_where.time_on_site || "—"}</div></div>
                  <div><FL>SLA Status</FL><div style={{ fontSize:11, color:T.ink, fontWeight:600 }}>{esc.who_and_where.sla_status || "—"}</div></div>
                  <div><FL>Evidence</FL><div style={{ fontSize:11, color:T.ink }}>{esc.evidence?.photos_uploaded || 0} photos · {esc.evidence?.docs_uploaded || 0} docs</div></div>
                </div>
              )}
              {esc.narrative && (
                <div style={{ background:T.paperDark, borderRadius:4, padding:"9px 12px", border:`1px solid ${T.border}` }}>
                  <FL>AI Escalation Narrative</FL>
                  <div style={{ fontSize:12, color:T.ink2, lineHeight:1.75, fontStyle:"italic" }}>"{esc.narrative}"</div>
                </div>
              )}
            </>
          ) : apr ? (
            <>
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr 1fr", gap:14, marginBottom:apr.tech_notes?14:0 }}>
                <div><FL>Fix Type</FL><div style={{ fontSize:12, color:T.ink, fontWeight:500 }}>{apr.fix_type==="short_term"?"Short Term":"Long Term"}</div></div>
                <div><FL>Action</FL><div style={{ fontSize:12, color:T.ink, fontWeight:500 }}>{(apr.action_taken||"").replace(/_/g," ")}</div></div>
                <div><FL>Labor</FL><div style={{ fontSize:12, color:T.ink, fontFamily:"monospace" }}>{apr.labor_hours}h</div></div>
                <div><FL>Parts Used</FL><div style={{ fontSize:11, color:T.ink }}>{(apr.parts_actually_used||[]).join(", ")||"—"}</div></div>
                {apr.test_results && (
                  <div style={{ gridColumn:"span 4" }}>
                    <FL>Test Results</FL>
                    <div style={{ fontSize:12, color:T.ink, lineHeight:1.7 }}>{apr.test_results}</div>
                  </div>
                )}
                {apr.ai_diagnosis_correct && (
                  <div>
                    <FL>AI Accuracy</FL>
                    <Tag alert={apr.ai_diagnosis_correct==="no"} dim={apr.ai_diagnosis_correct!=="no"}>
                      {apr.ai_diagnosis_correct==="yes"?"AI CORRECT":apr.ai_diagnosis_correct==="partially"?"PARTIAL":"AI INCORRECT"}
                    </Tag>
                  </div>
                )}
                {apr.safety_confirmed != null && (
                  <div>
                    <FL>Safety Check</FL>
                    <Tag dim>{apr.safety_confirmed?"SAFE TO OPERATE ✓":"NOT CONFIRMED"}</Tag>
                  </div>
                )}
              </div>
              {apr.tech_notes && (
                <div style={{ background:T.paperDark, borderRadius:4, padding:"9px 12px", border:`1px solid ${T.border}` }}>
                  <FL>Tech Notes</FL>
                  <div style={{ fontSize:12, color:T.ink2, lineHeight:1.75, fontStyle:"italic" }}>"{apr.tech_notes}"</div>
                </div>
              )}
            </>
          ) : (
            <div style={{ fontSize:12, color:T.ink4, fontStyle:"italic" }}>No submission data yet.</div>
          )}
        </div>

        {/* DECISION */}
        <div style={{ background:isClosed?T.paperDark:T.paper, borderRadius:6, padding:"15px 18px", marginBottom:10, border:`1px solid ${isClosed?T.borderMid:T.border}` }}>
          <FL>{isEsc?"Escalation Decision":"Approval Decision"}</FL>

          {isClosed ? (
            <div style={{ display:"flex", alignItems:"center", gap:12 }}>
              <span style={{ fontSize:16, color:T.ink3 }}>✓</span>
              <div>
                <div style={{ fontSize:13, fontWeight:700, color:T.ink }}>Case Closed</div>
                <div style={{ fontSize:11, color:T.ink4, marginTop:1 }}>Ticket {ticket.ticket_id} · {ticket.status}</div>
              </div>
            </div>
          ) : isEsc ? (
            <div style={{ fontSize:12, color:T.ink3 }}>
              Escalation pending factory or senior response. Use{" "}
              <strong style={{ color:T.ink }}>Assign Ticket</strong> to dispatch a technician.
            </div>
          ) : apr?.status === "pending" ? (
            <>
              {saveErr && <ErrBox msg={saveErr}/>}
              <div style={{ marginBottom:12 }}>
                <FL>Reviewer Comment</FL>
                <input
                  value={note} onChange={e=>setNote(e.target.value)}
                  placeholder="Feedback for technician (required if rejecting)…"
                  style={{ width:"100%", padding:"8px 11px", border:`1px solid ${T.border}`, borderRadius:4, fontSize:12, outline:"none", color:T.ink, background:T.paperDark, fontFamily:"inherit", boxSizing:"border-box" }}
                />
              </div>
              <div style={{ display:"flex", gap:8 }}>
                <button onClick={()=>reviewApproval("approved")} disabled={saving} style={{ flex:1, padding:"10px 0", background:saving?T.paperDark:T.void, color:saving?T.ink4:T.white, border:`1px solid ${saving?T.border:"#2a2a2a"}`, borderRadius:4, fontSize:12, fontWeight:700, cursor:saving?"default":"pointer" }}>
                  ✓ Approve & Close
                </button>
                <button onClick={()=>reviewApproval("rejected")} disabled={saving} style={{ flex:1, padding:"10px 0", background:"transparent", color:saving?T.ink4:T.red, border:`1.5px solid ${saving?T.border:T.red+"55"}`, borderRadius:4, fontSize:12, fontWeight:700, cursor:saving?"default":"pointer" }}>
                  ↩ Return for Rework
                </button>
              </div>
              {apr.fix_type==="short_term" && (
                <div style={{ fontSize:10, color:T.ink4, marginTop:8, fontStyle:"italic" }}>⚠ Short-term fix — approval will prompt a follow-up job.</div>
              )}
            </>
          ) : (
            <div style={{ fontSize:12, color:T.ink4, fontStyle:"italic" }}>
              {apr ? `Approval status: ${apr.status}` : "No approval request submitted yet."}
            </div>
          )}
        </div>

        {/* RCA STEPS */}
        {(rca?.steps?.length > 0 || rcaSkip) && (
          <>
            <Rule label="Root Cause Analysis"/>
            {rcaSkip ? (
              <div style={{ background:T.paper, borderRadius:5, padding:"11px 14px", border:`1px solid ${T.border}`, marginBottom:10 }}>
                <FL>RCA Skipped</FL>
                <div style={{ fontSize:12, color:T.ink2 }}>{rcaSkip.reason || "No reason given"}</div>
              </div>
            ) : (
              <div style={{ border:`1px solid ${T.border}`, borderRadius:5, overflow:"hidden", marginBottom:10 }}>
                {(rca.steps||[]).map((step,i) => {
                  const s = RCA_ICONS[step.status] || { s:"·", c:T.ink3 };
                  return (
                    <div key={i} style={{ display:"flex", borderBottom:i<rca.steps.length-1?`1px solid ${T.border}`:"none", background:i%2===0?T.paper:T.paperDark }}>
                      <div style={{ width:52, flexShrink:0, borderRight:`1px solid ${T.border}`, padding:"11px 0", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:4 }}>
                        <span style={{ fontSize:9, color:T.ink4, fontFamily:"monospace" }}>{String(i+1).padStart(2,"0")}</span>
                        <span style={{ fontSize:13, color:s.c, fontWeight:700 }}>{s.s}</span>
                      </div>
                      <div style={{ padding:"10px 14px", flex:1 }}>
                        <div style={{ fontSize:11, fontWeight:700, color:T.ink, marginBottom:3 }}>{step.label || step.step_label || `Step ${i+1}`}</div>
                        <div style={{ fontSize:11, color:T.ink3, lineHeight:1.6 }}>{step.result || step.finding || "—"}</div>
                        {step.note && <div style={{ fontSize:10, color:T.ink3, marginTop:4, fontStyle:"italic" }}>{step.note}</div>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* AI TRIAGE LOG */}
        {(diag.narrative || parts.length > 0 || (safety.warnings||[]).length > 0) && (
          <div style={{ background:T.paper, borderRadius:6, overflow:"hidden", border:`1px solid ${T.border}` }}>
            <div style={{ padding:"12px 18px 10px", borderBottom:`1px solid ${T.border}`, display:"flex", justifyContent:"space-between", alignItems:"center", background:T.paperDark }}>
              <div>
                <FL>AI Triage Log</FL>
                <div style={{ fontSize:10, color:T.ink4 }}>Generated {fmtTime(triage.saved_at)}</div>
              </div>
              <div style={{ display:"flex", background:T.void, borderRadius:3, overflow:"hidden", border:`1px solid #1E1E1E` }}>
                {[["summary","Summary"],["detail","Full Detail"]].map(([id,lab]) => (
                  <button key={id} onClick={()=>setAiView(id)} style={{ padding:"5px 13px", border:"none", cursor:"pointer", fontSize:10, fontWeight:700, background:aiView===id?T.red:"transparent", color:aiView===id?T.white:"#383838" }}>{lab}</button>
                ))}
              </div>
            </div>

            {aiView==="summary" && (
              <div style={{ padding:"16px 18px" }}>
                <div style={{ display:"flex", marginBottom:14, border:`1px solid ${T.border}`, borderRadius:5, overflow:"hidden" }}>
                  <div style={{ padding:"12px 16px", borderRight:`1px solid ${T.border}`, background:sev.priority==="P1"?T.redBg:T.paperDark, minWidth:80, textAlign:"center" }}>
                    <FL>Priority</FL>
                    <div style={{ fontSize:26, fontWeight:900, color:sev.priority==="P1"?T.red:T.ink2, lineHeight:1, fontFamily:"monospace" }}>{sev.priority||"—"}</div>
                    <div style={{ fontSize:9, color:T.ink4, marginTop:3 }}>SLA {sev.sla_hours||"—"}h</div>
                  </div>
                  <div style={{ padding:"12px 16px", flex:1, display:"flex", alignItems:"center" }}>
                    <div style={{ fontSize:12, color:T.ink2, lineHeight:1.7 }}>{sev.impact || diag.summary || "—"}</div>
                  </div>
                </div>
                {(safety.warnings||[]).length > 0 && (
                  <div style={{ background:T.redBg, border:`1px solid ${T.redBorder}`, borderRadius:5, padding:"10px 13px", marginBottom:13 }}>
                    <FL>⚠ Safety Flags</FL>
                    {safety.warnings.map((w,i) => <div key={i} style={{ fontSize:11, color:T.red, lineHeight:1.65, marginBottom:3 }}>• {w}</div>)}
                  </div>
                )}
                {diag.narrative && (
                  <>
                    <FL>AI Summary</FL>
                    <div style={{ fontSize:12, color:T.ink, lineHeight:1.85, padding:"12px 14px", background:T.paperDark, borderRadius:5, border:`1px solid ${T.border}` }}>{diag.narrative}</div>
                  </>
                )}
              </div>
            )}

            {aiView==="detail" && (
              <div style={{ padding:"16px 18px" }}>
                {diag.narrative && (
                  <>
                    <FL>Full Diagnosis</FL>
                    <div style={{ fontSize:12, color:T.ink2, lineHeight:1.85, marginBottom:12 }}>{diag.narrative}</div>
                  </>
                )}
                {parts.length > 0 && (
                  <>
                    <Rule label="Predicted Parts"/>
                    {parts.map((p,i) => (
                      <div key={i} style={{ display:"flex", alignItems:"center", gap:10, padding:"9px 12px", background:T.paperDark, borderRadius:4, border:`1px solid ${T.border}`, marginBottom:6 }}>
                        <div style={{ width:42, flexShrink:0 }}>
                          <div style={{ height:3, background:T.border, borderRadius:2, overflow:"hidden", marginBottom:3 }}>
                            <div style={{ width:`${p.confidence||0}%`, height:"100%", background:(p.confidence||0)>80?T.ink:T.ink3, borderRadius:2 }}/>
                          </div>
                          <div style={{ fontSize:9, color:T.ink4, fontFamily:"monospace", textAlign:"center" }}>{p.confidence||0}%</div>
                        </div>
                        <div style={{ flex:1 }}><div style={{ fontSize:12, fontWeight:600, color:T.ink }}>{p.description}</div></div>
                        <div style={{ fontSize:9, color:T.ink4, fontFamily:"monospace" }}>{p.part_number}</div>
                      </div>
                    ))}
                  </>
                )}
                {(safety.warnings||[]).length > 0 && (
                  <>
                    <Rule label="Safety Flags"/>
                    {safety.warnings.map((w,i) => (
                      <div key={i} style={{ display:"flex", gap:8, marginBottom:7 }}>
                        <span style={{ color:T.red, fontWeight:800 }}>⚠</span>
                        <div style={{ fontSize:12, color:T.ink, lineHeight:1.65 }}>{w}</div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── ASSIGN TICKET ─────────────────────────────────────────────────────────────
const SERIALS = [
  { sn:"X15-CM2450-0001", model:"X15 Performance", customer:"Summit Construction LLC" },
  { sn:"X15-CM2450-0002", model:"X15 Performance", customer:"Hartwell Mining Co." },
  { sn:"X15-CM2450-0003", model:"X15 Efficiency",  customer:"Ridgeline Forestry Inc." },
  { sn:"X15-CM2450-0004", model:"X15 Performance", customer:"Blackrock Quarrying Ltd." },
  { sn:"X15-CM2350-0005", model:"X15 Efficiency",  customer:"Cascade Aggregate Corp." },
  { sn:"X15-CM2350-0006", model:"X15 Efficiency",  customer:"Ironwood Land Clearing" },
  { sn:"X15-CM2450-0007", model:"X15 Performance", customer:"BlueSky Earthworks" },
  { sn:"X15-CM2450-0008", model:"X15 Performance", customer:"Titan Demolition Services" },
  { sn:"X15-CM2350-0009", model:"X15 Efficiency",  customer:"Greenfield Pipeline Co." },
  { sn:"X15-CM2450-0010", model:"X15 Performance", customer:"Apex Logging & Timber" },
  { sn:"X15-CM2450-0011", model:"X15 Efficiency",  customer:"Redstone Drilling Inc." },
  { sn:"X15-CM2350-0012", model:"X15 Efficiency",  customer:"Northern Gravel Works" },
];

function AssignTicket({ managers }) {
  const STEPS = { form:0, recommendation:1, dispatched:2 };
  const [step, setStep]             = useState(STEPS.form);
  const [loading, setLoading]       = useState(false);
  const [loadingMsg, setLoadingMsg] = useState("");
  const [error, setError]           = useState("");
  const [selectedSerial, setSerial] = useState("");
  const [form, setForm]             = useState({ location:"", issue_description:"" });
  const [triageResult, setTriage]   = useState(null);
  const [ticketId, setTicketId]     = useState(null);
  const [recommendations, setRecs]  = useState(null);
  const [selectedTech, setTech]     = useState(null);
  const [selectedMgr, setMgr]       = useState("");
  const [isOverride, setOverride]   = useState(false);
  const [overrideReason, setOR]     = useState("");
  const [dispatched, setDispatched] = useState(null);

  useEffect(() => {
    if (managers.length > 0 && !selectedMgr) setMgr(managers[0].manager_id || managers[0].id || "");
  }, [managers]);

  const serialInfo = SERIALS.find(s => s.sn === selectedSerial);
  const set = (k,v) => setForm(f => ({...f,[k]:v}));

  const runAnalysis = async () => {
    if (!selectedSerial || !form.location || !form.issue_description) {
      setError("Please fill in all fields."); return;
    }
    setError(""); setLoading(true);
    try {
      setLoadingMsg("Running AI triage…");
      const tr = await fetch(`${API}/api/triage`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          customer:          serialInfo.customer,
          location:          form.location,
          serial_number:     selectedSerial,
          issue_description: form.issue_description,
          tech_id:           "UNASSIGNED",
        }),
      });
      const td = await tr.json();
      if (!td.success) throw new Error(td.detail || "Triage failed");
      const tid = td.ticket_id;
      setTicketId(tid); setTriage(td);

      setLoadingMsg("Scoring technicians…");
      const ar = await fetch(`${API}/api/assign/${tid}`);
      const ad = await ar.json();
      if (!ad.success) throw new Error(ad.detail || "Assignment failed");
      setRecs(ad);

      setStep(STEPS.recommendation);
    } catch (e) {
      setError(e.message || "Backend unreachable — is FastAPI running?");
    }
    setLoading(false); setLoadingMsg("");
  };

  const dispatch = async () => {
    if (!selectedTech) { setError("Select a technician first."); return; }
    if (isOverride && !overrideReason) { setError("Override reason required."); return; }
    const mgr = managers.find(m => (m.manager_id||m.id) === selectedMgr);
    setError(""); setLoading(true);
    try {
      const r = await fetch(`${API}/api/assign/${ticketId}/approve`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          ticket_id:       ticketId,
          tech_id:         selectedTech.tech_id,
          approver_id:     selectedMgr,
          approver_name:   mgr?.name || selectedMgr,
          is_override:     isOverride,
          override_reason: isOverride ? overrideReason : null,
        }),
      });
      const d = await r.json();
      if (!d.success) throw new Error(d.detail || "Dispatch failed");
      setDispatched(d); setStep(STEPS.dispatched);
    } catch (e) {
      setError(e.message || "Dispatch failed");
    }
    setLoading(false);
  };

  const reset = () => {
    setStep(STEPS.form); setForm({ location:"", issue_description:"" });
    setSerial(""); setTriage(null); setTicketId(null); setRecs(null);
    setTech(null); setDispatched(null); setOverride(false); setOR(""); setError(""); setLoadingMsg("");
  };

  const StepBar = () => (
    <div style={{ display:"flex", alignItems:"center", marginBottom:22 }}>
      {["Ticket Details","AI Recommendation","Dispatched"].map((label,i) => {
        const done=step>i, current=step===i;
        return (
          <div key={i} style={{ display:"flex", alignItems:"center", flex:i<2?1:"none" }}>
            <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:4 }}>
              <div style={{ width:26, height:26, borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:10, fontWeight:800, fontFamily:"monospace", background:done?T.ink:current?T.red:T.paperDark, color:done||current?T.white:T.ink4, border:`1.5px solid ${done?T.ink:current?T.red:T.border}` }}>
                {done?"✓":i+1}
              </div>
              <div style={{ fontSize:9, fontWeight:700, color:current?T.ink:done?T.ink3:T.ink4, whiteSpace:"nowrap" }}>{label}</div>
            </div>
            {i<2 && <div style={{ flex:1, height:1, background:step>i?T.ink:T.border, margin:"0 8px", marginBottom:14 }}/>}
          </div>
        );
      })}
    </div>
  );

  const tr   = triageResult;
  const tsev = tr?.triage_results?.severity  || {};
  const tdg  = tr?.triage_results?.diagnosis || {};
  const tsaf = tr?.triage_results?.safety    || {};

  return (
    <div style={{ flex:1, overflowY:"auto", padding:"24px 28px" }}>
      <div style={{ maxWidth:780, margin:"0 auto" }}>
        <div style={{ fontSize:18, fontWeight:800, color:T.ink, letterSpacing:-0.3, marginBottom:4 }}>Assign Ticket to Technician</div>
        <div style={{ fontSize:12, color:T.ink3, marginBottom:22 }}>Fill in the details — the AI analyses the fault and recommends the best available technician in one step.</div>

        <StepBar/>
        {error && <ErrBox msg={error}/>}

        {/* STEP 0: FORM */}
        {step===STEPS.form && (
          <div style={{ background:T.paper, borderRadius:8, padding:"20px 22px", border:`1px solid ${T.border}` }}>
            <div style={{ marginBottom:14 }}>
              <FL>Equipment Serial Number</FL>
              <select value={selectedSerial} onChange={e=>setSerial(e.target.value)} style={{ width:"100%", padding:"9px 12px", border:`1px solid ${T.border}`, borderRadius:5, fontSize:12, outline:"none", cursor:"pointer", background:T.paper, color:selectedSerial?T.ink:T.ink4 }}>
                <option value="">Select a registered serial number…</option>
                {SERIALS.map(s => <option key={s.sn} value={s.sn}>{s.sn} — {s.model} · {s.customer}</option>)}
              </select>
              {serialInfo && (
                <div style={{ display:"flex", gap:16, marginTop:8, padding:"8px 12px", background:T.paperDark, borderRadius:4, border:`1px solid ${T.border}` }}>
                  <div><FL>Customer</FL><div style={{ fontSize:12, color:T.ink, fontWeight:600 }}>{serialInfo.customer}</div></div>
                  <div><FL>Engine</FL><div style={{ fontSize:12, color:T.ink, fontWeight:600 }}>{serialInfo.model}</div></div>
                  <div><FL>Serial</FL><div style={{ fontSize:12, color:T.ink, fontFamily:"monospace" }}>{serialInfo.sn}</div></div>
                </div>
              )}
            </div>
            <div style={{ marginBottom:14 }}>
              <FL>Site / Location</FL>
              <input value={form.location} onChange={e=>set("location",e.target.value)} placeholder="e.g. Denver North Yard, Gate 4" style={{ width:"100%", padding:"9px 12px", border:`1px solid ${T.border}`, borderRadius:5, fontSize:12, outline:"none", color:T.ink, background:T.paper, boxSizing:"border-box" }}/>
            </div>
            <div style={{ marginBottom:20 }}>
              <FL>Issue Description</FL>
              <textarea value={form.issue_description} onChange={e=>set("issue_description",e.target.value)} placeholder="Describe the fault symptoms reported by the operator…" rows={3} style={{ width:"100%", padding:"9px 12px", border:`1px solid ${T.border}`, borderRadius:5, fontSize:12, outline:"none", resize:"none", color:T.ink, background:T.paper, fontFamily:"inherit", boxSizing:"border-box" }}/>
            </div>
            <button onClick={runAnalysis} disabled={loading} style={{ width:"100%", padding:"11px 0", background:loading?T.paperDark:T.void, color:loading?T.ink4:T.white, border:`1px solid ${loading?T.border:"#2a2a2a"}`, borderRadius:5, fontSize:13, fontWeight:700, cursor:loading?"default":"pointer", letterSpacing:0.8, display:"flex", alignItems:"center", justifyContent:"center", gap:8 }}>
              {loading ? loadingMsg||"Analysing…" : "⚡  Analyse & Get AI Recommendation"}
            </button>
            <div style={{ fontSize:10, color:T.ink4, textAlign:"center", marginTop:7 }}>Fault codes auto-read from ECM · ML model scores all available technicians</div>
          </div>
        )}

        {/* STEP 1: RECOMMENDATION */}
        {step===STEPS.recommendation && tr && recommendations && (
          <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
            {/* Triage card */}
            <div style={{ background:T.paper, borderRadius:8, overflow:"hidden", border:`1px solid ${T.border}` }}>
              <div style={{ display:"flex", borderBottom:`1px solid ${T.border}` }}>
                <div style={{ padding:"14px 18px", borderRight:`1px solid ${T.border}`, background:tsev.priority==="P1"?T.redBg:T.paperDark, minWidth:90, textAlign:"center" }}>
                  <FL>Priority</FL>
                  <div style={{ fontSize:28, fontWeight:900, color:tsev.priority==="P1"?T.red:T.ink2, lineHeight:1, fontFamily:"monospace" }}>{tsev.priority||"P2"}</div>
                  <div style={{ fontSize:9, color:T.ink4, marginTop:3 }}>SLA {tsev.sla_hours||"—"}h</div>
                </div>
                <div style={{ padding:"14px 18px", flex:1 }}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:8 }}>
                    <div><FL>Ticket Created</FL><div style={{ fontSize:12, fontWeight:800, color:T.ink, fontFamily:"monospace" }}>{ticketId}</div></div>
                    <div style={{ display:"flex", gap:6, flexWrap:"wrap", justifyContent:"flex-end" }}>
                      {(tr.ecm_auto_populated?.fault_codes||[]).map(fc => (
                        <span key={fc} style={{ fontSize:10, fontWeight:700, background:T.dark, color:"#606060", borderRadius:2, padding:"3px 9px", fontFamily:"monospace", border:`1px solid ${T.darkBorder}` }}>{fc}</span>
                      ))}
                      {tr.ecm_auto_populated?.derate_active   && <Tag alert>DERATE</Tag>}
                      {tr.ecm_auto_populated?.shutdown_active && <Tag alert>SHUTDOWN</Tag>}
                    </div>
                  </div>
                  <div style={{ display:"flex", gap:16, flexWrap:"wrap" }}>
                    {tr.ecm_auto_populated?.equipment_hours && <div><FL>Hours</FL><div style={{ fontSize:11, color:T.ink, fontFamily:"monospace", fontWeight:600 }}>{tr.ecm_auto_populated.equipment_hours.toLocaleString()}</div></div>}
                    {tr.ecm_auto_populated?.engine_model && <div><FL>Engine</FL><div style={{ fontSize:11, color:T.ink, fontWeight:600 }}>{tr.ecm_auto_populated.engine_model}</div></div>}
                    <div><FL>Customer</FL><div style={{ fontSize:11, color:T.ink, fontWeight:600 }}>{serialInfo?.customer}</div></div>
                    <div><FL>Location</FL><div style={{ fontSize:11, color:T.ink }}>{form.location}</div></div>
                  </div>
                </div>
              </div>
              {tdg.narrative && (
                <div style={{ padding:"12px 18px", borderBottom:(tsaf.warnings||[]).length>0?`1px solid ${T.border}`:"none" }}>
                  <FL>AI Diagnosis</FL>
                  <div style={{ fontSize:12, color:T.ink2, lineHeight:1.8 }}>{tdg.narrative}</div>
                </div>
              )}
              {(tsaf.warnings||[]).length > 0 && (
                <div style={{ padding:"11px 18px", background:T.redBg }}>
                  <FL>⚠ Safety Flags</FL>
                  {tsaf.warnings.map((w,i) => <div key={i} style={{ fontSize:11, color:T.red, lineHeight:1.65, marginBottom:3 }}>• {w}</div>)}
                </div>
              )}
            </div>

            <Rule label="AI Recommends — Select a Technician"/>

            {/* Model metadata */}
            <div style={{ display:"flex", gap:20, padding:"0 2px", marginBottom:2 }}>
              {recommendations.model_info?.ftf_accuracy && <span style={{ fontSize:9, color:T.ink4, fontFamily:"monospace" }}>FTF accuracy {(recommendations.model_info.ftf_accuracy*100).toFixed(1)}%</span>}
              {recommendations.model_info?.sla_accuracy && <span style={{ fontSize:9, color:T.ink4, fontFamily:"monospace" }}>SLA accuracy {(recommendations.model_info.sla_accuracy*100).toFixed(1)}%</span>}
              {recommendations.model_info?.training_n   && <span style={{ fontSize:9, color:T.ink4, fontFamily:"monospace" }}>trained on {recommendations.model_info.training_n} records</span>}
              <span style={{ fontSize:9, color:T.ink4, fontFamily:"monospace" }}>{recommendations.total_evaluated||"—"} technicians evaluated</span>
            </div>

            {/* Tech cards */}
            {(recommendations.recommendations||[]).map((rec,i) => {
              const isSel = selectedTech?.tech_id===rec.tech_id;
              const isTop = i===0;
              return (
                <div key={rec.tech_id} onClick={()=>setTech(isSel?null:rec)} style={{ background:T.paper, borderRadius:8, padding:"16px 20px", border:`1.5px solid ${isSel?T.ink:isTop?T.borderMid:T.border}`, cursor:"pointer", boxShadow:isSel?`0 0 0 1px ${T.ink}`:"none" }}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:12 }}>
                    <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                      <div style={{ width:36, height:36, borderRadius:"50%", background:isTop?T.dark:T.paperDark, border:`1px solid ${T.border}`, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
                        <span style={{ fontSize:13, fontWeight:800, color:isTop?T.white:T.ink3, fontFamily:"monospace" }}>#{i+1}</span>
                      </div>
                      <div>
                        <div style={{ fontSize:15, fontWeight:800, color:T.ink }}>{rec.tech_name}</div>
                        <div style={{ fontSize:10, color:T.ink4, marginTop:1 }}>{rec.depot} · Level {rec.cert_level} · {rec.proximity_km}km away</div>
                      </div>
                    </div>
                    <div style={{ display:"flex", gap:16, alignItems:"center" }}>
                      {[["FTF PROB",rec.ftf_probability],["SLA PROB",rec.sla_probability]].map(([lab,val])=>(
                        <div key={lab} style={{ textAlign:"center" }}>
                          <div style={{ fontSize:8, color:T.ink4, fontFamily:"monospace", letterSpacing:1, marginBottom:4 }}>{lab}</div>
                          <div style={{ width:80, height:6, background:T.border, borderRadius:3, overflow:"hidden", marginBottom:3 }}>
                            <div style={{ width:`${val*100}%`, height:"100%", background:val>0.75?T.ink:val>0.55?T.ink2:T.ink3, borderRadius:3 }}/>
                          </div>
                          <div style={{ fontSize:13, fontWeight:800, color:T.ink, fontFamily:"monospace" }}>{(val*100).toFixed(0)}%</div>
                        </div>
                      ))}
                      {isSel && <div style={{ width:22, height:22, borderRadius:"50%", background:T.ink, display:"flex", alignItems:"center", justifyContent:"center" }}><span style={{ color:T.white, fontSize:11 }}>✓</span></div>}
                    </div>
                  </div>
                  <div style={{ display:"flex", gap:14, marginBottom:10, flexWrap:"wrap" }}>
                    {[["Workload",rec.active_tickets===0?"Available":`${rec.active_tickets} active`],["System Exp.",rec.fault_experience>0?`${rec.fault_experience} jobs`:"None"],["Success Rate",`${(rec.prior_success_rate*100).toFixed(0)}%`],["Specialization",rec.has_specialization?rec.fault_system:"None"]].map(([l,v])=>(
                      <div key={l}><div style={{ fontSize:8, fontWeight:800, color:T.ink4, letterSpacing:1.2, fontFamily:"monospace" }}>{l}</div><div style={{ fontSize:11, color:T.ink2, fontWeight:600, marginTop:1 }}>{v}</div></div>
                    ))}
                  </div>
                  <div style={{ fontSize:11, color:T.ink3, lineHeight:1.65, background:T.paperDark, padding:"8px 11px", borderRadius:4, border:`1px solid ${T.border}` }}>{rec.reasoning}</div>
                </div>
              );
            })}

            {/* Override */}
            <div style={{ background:T.paper, borderRadius:6, padding:"12px 16px", border:`1px solid ${T.border}` }}>
              <label style={{ display:"flex", alignItems:"center", gap:8, cursor:"pointer", fontSize:12, color:T.ink2 }}>
                <input type="checkbox" checked={isOverride} onChange={e=>setOverride(e.target.checked)} style={{ width:14, height:14, cursor:"pointer" }}/>
                Dispatcher override — assign someone not recommended by the model
              </label>
              {isOverride && <input value={overrideReason} onChange={e=>setOR(e.target.value)} placeholder="Reason for override…" style={{ width:"100%", marginTop:8, padding:"7px 10px", border:`1px solid ${T.border}`, borderRadius:4, fontSize:12, outline:"none", color:T.ink, background:T.paperDark, fontFamily:"inherit", boxSizing:"border-box" }}/>}
            </div>

            {/* Manager + dispatch */}
            <div style={{ background:T.paper, borderRadius:6, padding:"14px 16px", border:`1px solid ${T.border}` }}>
              <FL>Approving Manager</FL>
              <select value={selectedMgr} onChange={e=>setMgr(e.target.value)} style={{ width:"100%", padding:"8px 11px", border:`1px solid ${T.border}`, borderRadius:4, fontSize:12, outline:"none", cursor:"pointer", background:T.paperDark, marginBottom:12 }}>
                {managers.map(m => <option key={m.manager_id||m.id} value={m.manager_id||m.id}>{m.name}</option>)}
              </select>
              <button onClick={dispatch} disabled={!selectedTech||loading} style={{ width:"100%", padding:"11px 0", background:!selectedTech||loading?T.paperDark:T.void, color:!selectedTech||loading?T.ink4:T.white, border:`1px solid ${!selectedTech||loading?T.border:"#2a2a2a"}`, borderRadius:5, fontSize:13, fontWeight:700, cursor:!selectedTech||loading?"default":"pointer", letterSpacing:0.8 }}>
                {loading?"Dispatching…":selectedTech?`Dispatch ${selectedTech.tech_name} →`:"Select a technician above"}
              </button>
            </div>
          </div>
        )}

        {/* STEP 2: DISPATCHED */}
        {step===STEPS.dispatched && dispatched && (
          <div style={{ textAlign:"center", padding:"40px 20px" }}>
            <div style={{ width:64, height:64, borderRadius:"50%", background:T.paperDark, border:`1.5px solid ${T.borderMid}`, display:"flex", alignItems:"center", justifyContent:"center", margin:"0 auto 18px" }}>
              <span style={{ fontSize:26, color:T.ink }}>✓</span>
            </div>
            <div style={{ fontSize:22, fontWeight:800, color:T.ink, letterSpacing:-0.3, marginBottom:8 }}>Technician Dispatched</div>
            <div style={{ fontSize:13, color:T.ink3, lineHeight:1.8, maxWidth:420, margin:"0 auto 24px" }}>
              <strong style={{ color:T.ink }}>{dispatched.tech_name}</strong> dispatched to <span style={{ fontFamily:"monospace", fontWeight:700 }}>{ticketId}</span>.
              {dispatched.is_override && <span style={{ color:T.red }}> (Override)</span>}
              <br/>Approved by {dispatched.approved_by}.
            </div>
            <div style={{ background:T.paper, border:`1px solid ${T.border}`, borderRadius:6, padding:"14px 20px", display:"inline-block", textAlign:"left", minWidth:320, marginBottom:24 }}>
              {[["Ticket",ticketId],["Technician",dispatched.tech_name],["Approved by",dispatched.approved_by],["Time",fmtTime(dispatched.dispatched_at)]].map(([l,v])=>(
                <div key={l} style={{ display:"flex", justifyContent:"space-between", gap:24, marginBottom:8 }}>
                  <span style={{ fontSize:10, fontWeight:800, color:T.ink4, fontFamily:"monospace", letterSpacing:1 }}>{l}</span>
                  <span style={{ fontSize:12, fontWeight:600, color:T.ink, fontFamily:l==="Ticket"?"monospace":"inherit" }}>{v}</span>
                </div>
              ))}
            </div>
            <br/>
            <button onClick={reset} style={{ padding:"10px 28px", background:T.void, color:T.white, border:"none", borderRadius:5, fontSize:12, fontWeight:700, cursor:"pointer", letterSpacing:0.8 }}>+ Assign Another Ticket</button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── ROOT ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [view, setView]         = useState("cases");
  const [tickets, setTickets]   = useState([]);
  const [managers, setManagers] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [activeCase, setActive] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/managers`)
      .then(r => r.json())
      .then(d => setManagers(d.managers || []))
      .catch(() => {});
  }, []);

  const loadSampleData = async () => {
    try {
      const sr = await fetch("/sample_cases.json");
      const sample = await sr.json();
      setTickets(sample);
      setActive(prev => prev || sample[0] || null);
    } catch (_) {}
  };

  const loadTickets = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/tickets`);
      const d = await r.json();
      const all = d.tickets || [];

      const full = await Promise.all(
        all.map(t =>
          fetch(`${API}/api/tickets/${t.ticket_id}`)
            .then(r => r.json())
            .catch(() => null)
        )
      );

      const actionable = full
        .filter(f => f && f.ticket)
        .filter(f => {
          const hasEsc  = f.escalation != null;
          const hasAppr = f.approval_request?.status === "pending";
          const isDone  = f.ticket.status === "resolved";
          return (hasEsc || hasAppr) && !isDone;
        });

      if (actionable.length === 0) {
        // No live data — load sample_cases.json for demo
        await loadSampleData();
      } else {
        setTickets(actionable);
        setActive(prev => {
          if (!prev) return actionable[0] || null;
          const updated = actionable.find(f => f.ticket.ticket_id === prev.ticket.ticket_id);
          return updated || actionable[0] || null;
        });
      }
    } catch (_) {
      // Backend unreachable — fall back to sample data
      await loadSampleData();
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadTickets();
    const id = setInterval(loadTickets, POLL_MS);
    return () => clearInterval(id);
  }, [loadTickets]);

  const pending = tickets.length;

  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100vh", overflow:"hidden", fontFamily:"'Segoe UI',system-ui,sans-serif" }}>
      <div style={{ background:T.void, height:46, display:"flex", alignItems:"center", justifyContent:"space-between", padding:"0 20px", flexShrink:0, borderBottom:`1px solid ${T.darkBorder}` }}>
        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
          <div style={{ width:3, height:20, background:T.red, borderRadius:1 }}/>
          <div>
            <div style={{ fontSize:12, fontWeight:900, color:T.white, letterSpacing:3.5, fontFamily:"monospace" }}>CUMMINS</div>
            <div style={{ fontSize:8, color:"#888888", letterSpacing:2.2, fontFamily:"monospace" }}>BACK OFFICE · CASE FILES</div>
          </div>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          {pending > 0 && (
            <div style={{ display:"flex", alignItems:"center", gap:5 }}>
              <span style={{ width:5, height:5, borderRadius:"50%", background:T.red }}/>
              <span style={{ fontSize:9, color:T.red, fontWeight:700, fontFamily:"monospace" }}>{pending} PENDING</span>
            </div>
          )}
          <span style={{ fontSize:8, color:"#666666", fontFamily:"monospace", letterSpacing:1 }}>LIVE · {API}</span>
        </div>
      </div>

      <div style={{ display:"flex", flex:1, overflow:"hidden" }}>
        <Sidebar active={view} onNav={setView} pendingCount={pending}/>

        {view==="cases" && (
          <>
            <CaseFeed tickets={tickets} loading={loading} activeId={activeCase?.ticket?.ticket_id} onSelect={setActive}/>
            {loading && !activeCase ? (
              <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", background:T.page }}>
                <div style={{ fontSize:11, color:T.ink4, fontFamily:"monospace" }}>Loading…</div>
              </div>
            ) : activeCase ? (
              <CaseFile key={activeCase.ticket.ticket_id} caseData={activeCase} onRefresh={loadTickets}/>
            ) : (
              <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", background:T.page }}>
                <div style={{ textAlign:"center", opacity:0.4 }}>
                  <div style={{ fontSize:36, marginBottom:10 }}>⬚</div>
                  <div style={{ fontSize:12, fontWeight:700, color:T.ink, letterSpacing:1 }}>NO PENDING CASES</div>
                  <div style={{ fontSize:11, color:T.ink3, marginTop:4 }}>All clear — nothing awaiting review</div>
                </div>
              </div>
            )}
          </>
        )}

        {view==="assign" && (
          <div style={{ flex:1, overflow:"hidden", display:"flex", flexDirection:"column", background:T.page }}>
            <AssignTicket managers={managers}/>
          </div>
        )}
      </div>
    </div>
  );
}