import { useState, useRef, useEffect, useCallback } from "react";

// ─── BACKEND URL ──────────────────────────────────────────────────────────────
const API = "http://localhost:8000";

// ─── EXACT FIGMA COLOR TOKENS ─────────────────────────────────────────────────
const T = {
  white:        "#FFFFFF",
  bgPage:       "#F2F2F2",
  bgLight:      "#FEF5F5",
  black:        "#1A1A1A",
  charcoal:     "#111111",
  gray1:        "#333333",
  gray2:        "#666666",
  gray3:        "#999999",
  gray4:        "#BBBBBB",
  border:       "#E0E0E0",
  borderLight:  "#F0F0F0",
  red:          "#D32F2F",
  redBg:        "#FFF0F0",
  redBorder:    "#F5C6C6",
  amber:        "#CF8300",
  amberDark:    "#917200",
  amberBg:      "#FFF8EC",
  amberBorder:  "#EFD080",
  green:        "#2E7D32",
  greenBg:      "#E8F5E9",
  greenBorder:  "#A5D6A7",
  blue:         "#1565C0",
  blueBg:       "#E3F2FD",
  yellowBg:     "#FFFDE7",
  yellowBorder: "#F9A825",
  chip:         "#1E1E1E",   // dark fault-code chips matching mockup
  chipText:     "#FFFFFF",
};

// (no hardcoded mock data — all loaded from backend API)

// ─── API ──────────────────────────────────────────────────────────────────────
async function apiHealth()       { return fetch(`${API}/`).then(r=>r.json()); }
async function apiListTickets()  { return fetch(`${API}/api/tickets`).then(r=>r.json()); }

async function apiChat(ticketId, message, lang="en", fileIds=[]) {
  const r = await fetch(`${API}/api/chat`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({ ticket_id:ticketId, message, language:lang, file_ids:fileIds }),
  });
  if (!r.ok) throw new Error();
  const d = await r.json();
  return d.response?.answer ?? d.response?.message ?? JSON.stringify(d.response);
}

async function apiListTechnicians() {
  const r = await fetch(`${API}/api/technicians`);
  return r.json();
}

async function apiRCAGenerate(ticketId) {
  const r = await fetch(`${API}/api/rca/${ticketId}`);
  return r.json();
}

async function apiRCAStep(ticketId, stepNumber, outcome, observation) {
  const r = await fetch(`${API}/api/rca/${ticketId}/step`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({ step_number:stepNumber, outcome, observation }),
  });
  return r.json();
}


async function apiRCAComplete(ticketId, finalOutcome) {
  const r = await fetch(`${API}/api/rca/${ticketId}/complete`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({ final_outcome:finalOutcome }),
  });
  return r.json();
}

async function apiRCASkip(ticketId, reason, reasonDetail, techId) {
  const r = await fetch(`${API}/api/rca/${ticketId}/skip`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({ reason, reason_detail:reasonDetail, tech_id:techId }),
  });
  return r.json();
}

async function apiEscalate(ticketId, body) {
  const r = await fetch(`${API}/api/escalate/${ticketId}`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body),
  });
  return r.json();
}

async function apiRequestApproval(ticketId, body) {
  const r = await fetch(`${API}/api/approve/${ticketId}`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body),
  });
  return r.json();
}

async function apiGetReports(techId) {
  const r = await fetch(`${API}/api/reports?tech_id=${encodeURIComponent(techId)}`);
  return r.json();
}

async function apiListManagers() {
  const r = await fetch(`${API}/api/managers`);
  return r.json();
}

async function apiListFaultCodes() {
  const r = await fetch(`${API}/api/fault_codes`);
  return r.json();
}

// ─── ATOMS ────────────────────────────────────────────────────────────────────
function PriorityBadge({ priority, ticket }) {
  const isHigh = priority==="High"||priority==="P1"||ticket?.derate_active||ticket?.shutdown_active;
  const bg = isHigh ? T.red : T.amber;
  const label = isHigh ? "P1" : "P2";
  return (
    <div style={{ background:bg, color:T.white, fontSize:10, fontWeight:800, padding:"3px 8px", borderRadius:4, letterSpacing:0.8 }}>
      {label}
    </div>
  );
}

function FaultChip({ code }) {
  return (
    <span style={{ fontSize:11, fontWeight:700, background:T.chip, color:T.chipText,
      borderRadius:4, padding:"3px 8px", letterSpacing:0.3 }}>{code}</span>
  );
}

function Label({ children, color, extra }) {
  return <div style={{ fontSize:9, fontWeight:800, color:color||T.gray2, letterSpacing:1.2, marginBottom:6, textTransform:"uppercase", ...extra }}>{children}</div>;
}

function Row({ label, value, vc }) {
  return (
    <div style={{ display:"flex", justifyContent:"space-between", paddingBottom:5, marginBottom:5, borderBottom:`1px solid ${T.bgPage}` }}>
      <span style={{ fontSize:11, color:T.gray3, fontWeight:500 }}>{label}</span>
      <span style={{ fontSize:11, color:vc||T.gray1, fontWeight:700 }}>{value}</span>
    </div>
  );
}

function Card({ children, style }) {
  return <div style={{ background:T.white, borderRadius:8, padding:"14px 16px", marginBottom:8, boxShadow:"0 1px 3px rgba(0,0,0,0.04)", ...style }}>{children}</div>;
}

function Chip({ label, active, onPress, color }) {
  const ac = color || T.black;
  return (
    <button onClick={onPress} style={{ padding:"7px 14px", borderRadius:6, fontSize:12, fontWeight:600, cursor:"pointer",
      border:`${active?"2":"1"}px solid ${active?ac:T.border}`,
      background:active?ac:T.white, color:active?T.white:T.gray2 }}>
      {label}
    </button>
  );
}

function SectionHeader({ title }) {
  return <div style={{ fontSize:9, fontWeight:800, color:T.gray3, letterSpacing:1.2, padding:"14px 16px 6px", textTransform:"uppercase" }}>{title}</div>;
}

// ─── BOTTOM NAV ───────────────────────────────────────────────────────────────
function BottomNav({ active, onNav }) {
  const tabs = [
    { id:"home",    label:"Home",
      icon: a => <svg width="22" height="22" viewBox="0 0 24 24" fill={a?T.red:"none"} stroke={a?T.red:T.gray3} strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg> },
    { id:"tickets", label:"Troubleshoot",
      icon: a => <svg width="22" height="22" viewBox="0 0 24 24" fill={a?T.red:"none"} stroke={a?T.red:T.gray3} strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> },
    { id:"reports", label:"Reports",
      icon: a => <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={a?T.red:T.gray3} strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg> },
    { id:"settings", label:"Settings",
      icon: a => <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={a?T.red:T.gray3} strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82 1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> },
  ];
  return (
    <div style={{ display:"flex", borderTop:`1px solid ${T.border}`, background:T.white, paddingBottom:4, flexShrink:0 }}>
      {tabs.map(tb => {
        const a = active===tb.id;
        return (
          <button key={tb.id} onClick={() => onNav(tb.id)} style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", gap:2, padding:"8px 0", background:"none", border:"none", cursor:"pointer" }}>
            {tb.icon(a)}
            <span style={{ fontSize:10, color:a?T.red:T.gray3, fontWeight:a?700:400 }}>{tb.label}</span>
          </button>
        );
      })}
    </div>
  );
}

// ─── TOP BAR ──────────────────────────────────────────────────────────────────
function TopBar({ onBack, rightEl }) {
  return (
    <div style={{ background:T.charcoal, color:T.white, display:"flex", alignItems:"center", justifyContent:"space-between", padding:"12px 16px", minHeight:52, flexShrink:0 }}>
      {onBack
        ? <button onClick={onBack} style={{ background:"none", border:"none", color:T.white, cursor:"pointer", padding:0 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
        : <button style={{ background:"none", border:"none", color:T.white, cursor:"pointer", padding:0 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
      }
      <span style={{ fontSize:14, fontWeight:900, letterSpacing:2.5 }}>CUMMINS</span>
      {rightEl ?? (
        <button style={{ background:"none", border:"none", color:T.white, cursor:"pointer", padding:0 }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        </button>
      )}
    </div>
  );
}

// ─── LOGIN ────────────────────────────────────────────────────────────────────
const SHARED_PASSWORD = "cummins2024";

function LoginScreen({ onLogin }) {
  const [techs, setTechs]       = useState([]);
  const [query, setQuery]       = useState("");
  const [selected, setSelected] = useState(null);
  const [password, setPassword] = useState("");
  const [err, setErr]           = useState("");

  useEffect(() => {
    apiListTechnicians()
      .then(d => setTechs(d.technicians || []))
      .catch(() => setErr("Could not connect to server."));
  }, []);

  const matches = query.trim().length > 0
    ? techs.filter(t =>
        t.name.toLowerCase().includes(query.toLowerCase()) ||
        t.tech_id.toLowerCase().includes(query.toLowerCase())
      )
    : [];

  const attempt = () => {
    if (!selected) { setErr("Select your name first."); return; }
    if (password !== SHARED_PASSWORD) { setErr("Incorrect password."); setPassword(""); return; }
    onLogin(selected);
  };

  return (
    <div style={{ flex:1, background:T.black, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:32, gap:20 }}>
      <div style={{ textAlign:"center" }}>
        <div style={{ fontSize:28, fontWeight:900, color:T.white, letterSpacing:3 }}>CUMMINS</div>
        <div style={{ fontSize:11, color:"#555", letterSpacing:1.5, marginTop:4 }}>SERVICE ENGINEERING</div>
      </div>

      <div style={{ width:"100%" }}>
        <div style={{ fontSize:10, fontWeight:700, color:"#555", letterSpacing:1, marginBottom:8 }}>YOUR NAME OR ID</div>
        <input
          value={selected ? selected.name : query}
          onChange={e => { setQuery(e.target.value); setSelected(null); setErr(""); }}
          placeholder="e.g. Marcus Johnson or TECH-014"
          style={{ width:"100%", padding:"14px 16px", borderRadius:10, border:`1px solid ${selected?"#D32F2F":"#2a2a2a"}`,
            background:"#111", color:T.white, fontSize:14, outline:"none" }}
        />
        {/* Dropdown suggestions */}
        {!selected && matches.length > 0 && (
          <div style={{ background:"#1a1a1a", border:"1px solid #2a2a2a", borderRadius:10, marginTop:4, overflow:"hidden" }}>
            {matches.slice(0,5).map(t => (
              <button key={t.tech_id} onClick={() => { setSelected(t); setQuery(""); setErr(""); }}
                style={{ width:"100%", padding:"12px 16px", background:"none", border:"none", borderBottom:"1px solid #2a2a2a",
                  cursor:"pointer", textAlign:"left" }}>
                <div style={{ fontSize:13, fontWeight:700, color:T.white }}>{t.name}</div>
                <div style={{ fontSize:11, color:"#555" }}>{t.tech_id} · Level {t.certification_level} · {t.depot}</div>
              </button>
            ))}
          </div>
        )}
        {selected && (
          <div style={{ marginTop:6, fontSize:11, color:"#555" }}>
            {selected.tech_id} · Level {selected.certification_level} · {selected.depot}
            <button onClick={() => { setSelected(null); setQuery(""); setPassword(""); }}
              style={{ marginLeft:8, background:"none", border:"none", color:"#555", cursor:"pointer", fontSize:11, textDecoration:"underline" }}>
              change
            </button>
          </div>
        )}
      </div>

      {selected && (
        <div style={{ width:"100%", display:"flex", flexDirection:"column", gap:10 }}>
          <div style={{ fontSize:10, fontWeight:700, color:"#555", letterSpacing:1 }}>PASSWORD</div>
          <input type="password" value={password} onChange={e=>setPassword(e.target.value)} onKeyDown={e=>e.key==="Enter"&&attempt()}
            placeholder="Enter password"
            style={{ width:"100%", padding:"14px 16px", borderRadius:10, border:"1px solid #2a2a2a", background:"#111",
              color:T.white, fontSize:15, textAlign:"center", outline:"none" }}/>
          {err && <div style={{ fontSize:12, color:T.red, textAlign:"center" }}>{err}</div>}
          <button onClick={attempt}
            style={{ width:"100%", padding:15, background:T.red, color:T.white, border:"none", borderRadius:10, fontSize:14, fontWeight:800, cursor:"pointer", letterSpacing:1 }}>
            SIGN IN
          </button>
        </div>
      )}
      {err && !selected && <div style={{ fontSize:12, color:T.red, textAlign:"center" }}>{err}</div>}
    </div>
  );
}

// ─── HOME SCREEN ──────────────────────────────────────────────────────────────
function HomeScreen({ tickets=[], onSelectTicket, currentUser, ticketsLoading }) {
  const [filter, setFilter] = useState("ALL");
  const filters = ["ALL", "P1 ONLY", "OPEN"];

  const high = tickets.filter(t => t.priority==="High" || t.derate_active || t.shutdown_active);
  const filtered = filter==="P1 ONLY" ? high
    : filter==="OPEN" ? tickets.filter(t => t.status !== "resolved")
    : tickets;

  const completed = tickets.filter(t => t.status==="resolved").length;

  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%" }}>
      {/* Top bar */}
      <div style={{ background:T.charcoal, flexShrink:0 }}>
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"12px 16px 0" }}>
          <button style={{ background:"none", border:"none", color:T.white, cursor:"pointer", padding:0 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
          <span style={{ fontSize:14, fontWeight:900, color:T.white, letterSpacing:2.5 }}>CUMMINS</span>
          <button style={{ background:"none", border:"none", color:T.white, cursor:"pointer", padding:0 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
          </button>
        </div>
        {/* Welcome banner */}
        <div style={{ padding:"12px 16px 16px" }}>
          <div style={{ fontSize:12, color:T.gray3, fontWeight:500, marginBottom:3 }}>Welcome back,</div>
          <div style={{ fontSize:20, fontWeight:900, color:T.white, letterSpacing:0.2, marginBottom:4 }}>{currentUser?.name || "Technician"}</div>
          <div style={{ fontSize:11, color:T.gray3, fontWeight:500 }}>
            Technician ID: {currentUser?.tech_id || "—"}
            {currentUser?.depot ? ` · ${currentUser.depot}` : ""}
          </div>
        </div>
      </div>

      <div style={{ flex:1, overflowY:"auto", background:T.bgPage }}>

        {/* Stats row */}
        <div style={{ background:T.white, display:"flex", borderBottom:`1px solid ${T.border}`, marginBottom:8 }}>
          {[
            { label:"ACTIVE FAULTS", value:high.length, badge:high.length>0?`+${high.length} new`:null, bColor:T.red },
            { label:"TICKETS OPEN",  value:tickets.length, badge:null },
            { label:"COMPLETED",     value:completed, badge:completed>0?`+${completed} today`:null, bColor:T.green },
          ].map((s,i)=>(
            <div key={i} style={{ flex:1, padding:"12px 8px", textAlign:"center", borderRight:i<2?`1px solid ${T.border}`:"none" }}>
              <div style={{ fontSize:22, fontWeight:900, color:T.black }}>{s.value}</div>
              {s.badge && <div style={{ fontSize:9, fontWeight:700, color:s.bColor, letterSpacing:0.3 }}>{s.badge}</div>}
              <div style={{ fontSize:9, color:T.gray3, fontWeight:600, letterSpacing:0.5, marginTop:2 }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Active faults header + filter */}
        <div style={{ padding:"4px 16px 8px", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
          <span style={{ fontSize:13, fontWeight:800, color:T.black }}>Tickets</span>
          <span style={{ fontSize:10, fontWeight:600, color:T.gray3 }}>{currentUser?.tech_id}</span>
        </div>

        {/* Filter pills */}
        <div style={{ padding:"0 16px 10px", display:"flex", gap:6 }}>
          {filters.map(f=>(
            <button key={f} onClick={()=>setFilter(f)}
              style={{ padding:"4px 12px", borderRadius:4, fontSize:11, fontWeight:700, cursor:"pointer", border:"none",
                background:filter===f?T.black:T.white, color:filter===f?T.white:T.gray2,
                boxShadow:filter===f?"none":`0 0 0 1px ${T.border}` }}>
              {f}
            </button>
          ))}
        </div>

        {/* Section label */}
        {!ticketsLoading && filtered.length>0 && (
          <div style={{ padding:"0 16px 6px" }}>
            <span style={{ fontSize:10, fontWeight:700, color:T.gray3, letterSpacing:0.8 }}>ACTIVE · {filtered.length} TICKET{filtered.length!==1?"S":""}</span>
          </div>
        )}

        {/* Ticket list */}
        <div style={{ padding:"0 12px 16px" }}>
          {ticketsLoading
            ? <div style={{ padding:"40px 0", textAlign:"center", fontSize:13, color:T.gray3 }}>Loading tickets…</div>
            : filtered.length===0
            ? <div style={{ padding:"40px 0", textAlign:"center", fontSize:13, color:T.gray3 }}>No tickets found.</div>
            : filtered.map(t => <TicketCard key={t.ticket_id} ticket={t} onPress={() => onSelectTicket(t)}/>)
          }
        </div>
      </div>
    </div>
  );
}

// ─── TICKETS SCREEN ───────────────────────────────────────────────────────────
function TicketsScreen({ tickets=[], onSelect }) {
  const [filter, setFilter] = useState("ALL");
  const filters = ["ALL", "P1 ONLY", "OPEN"];
  const filtered = filter==="P1 ONLY" ? tickets.filter(t=>t.priority==="High"||t.derate_active)
    : filter==="OPEN" ? tickets.filter(t=>t.status!=="resolved")
    : tickets;
  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%" }}>
      <div style={{ background:T.charcoal, display:"flex", alignItems:"center", justifyContent:"space-between", padding:"12px 16px", flexShrink:0 }}>
        <button style={{ background:"none", border:"none", color:T.white, cursor:"pointer", padding:0 }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <span style={{ fontSize:14, fontWeight:900, color:T.white, letterSpacing:2.5 }}>CUMMINS</span>
        <button style={{ background:"none", border:"none", color:T.white, cursor:"pointer", padding:0 }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        </button>
      </div>
      <div style={{ background:T.white, padding:"10px 16px 0", borderBottom:`1px solid ${T.border}`, flexShrink:0 }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:8 }}>
          <span style={{ fontSize:16, fontWeight:900, color:T.black }}>Tickets</span>
          <span style={{ fontSize:10, fontWeight:600, color:T.gray3 }}>{filtered.length} active</span>
        </div>
        <div style={{ display:"flex", gap:6, paddingBottom:10 }}>
          {filters.map(f=>(
            <button key={f} onClick={()=>setFilter(f)}
              style={{ padding:"4px 12px", borderRadius:4, fontSize:11, fontWeight:700, cursor:"pointer", border:"none",
                background:filter===f?T.black:T.white, color:filter===f?T.white:T.gray2,
                boxShadow:filter===f?"none":`0 0 0 1px ${T.border}` }}>
              {f}
            </button>
          ))}
        </div>
      </div>
      {filtered.length>0 && (
        <div style={{ padding:"8px 16px 4px", background:T.bgPage }}>
          <span style={{ fontSize:10, fontWeight:700, color:T.gray3, letterSpacing:0.8 }}>ACTIVE · {filtered.length} TICKET{filtered.length!==1?"S":""}</span>
        </div>
      )}
      <div style={{ flex:1, overflowY:"auto", background:T.bgPage, padding:"4px 12px 12px" }}>
        {filtered.map(t => <TicketCard key={t.ticket_id} ticket={t} onPress={() => onSelect(t)}/>)}
      </div>
    </div>
  );
}

function TicketCard({ ticket:t, onPress }) {
  const isHigh = t.priority==="High" || t.derate_active || t.shutdown_active;
  const badgeBg = isHigh ? T.red : T.amber;
  const systems = t.systems?.join(", ") || (t.fault_codes||[]).map(c=>FAULT_SYSTEM_MAP[c]).filter(Boolean).filter((v,i,a)=>a.indexOf(v)===i).join(", ");

  return (
    <button onClick={onPress} style={{ background:T.white, borderRadius:8, padding:"13px 14px 11px", border:`1px solid ${T.border}`, textAlign:"left", cursor:"pointer", width:"100%", marginBottom:8, display:"block" }}>
      {/* Row 1: ID + badge */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:5 }}>
        <span style={{ fontSize:10, color:T.gray3, fontWeight:600, letterSpacing:0.3 }}>{t.ticket_id}</span>
        <div style={{ background:badgeBg, color:T.white, fontSize:10, fontWeight:800, padding:"2px 9px", borderRadius:4, letterSpacing:0.8 }}>
          {isHigh ? "High" : "Medium"}
        </div>
      </div>

      {/* Row 2: Customer name */}
      <div style={{ fontSize:16, fontWeight:900, color:T.black, marginBottom:5, lineHeight:1.2 }}>{t.customer}</div>

      {/* Row 3: Location */}
      <div style={{ display:"flex", alignItems:"center", gap:4, marginBottom:7 }}>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={T.gray3} strokeWidth="2.5"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        <span style={{ fontSize:11, color:T.gray3 }}>{t.location} · {t.equipment_model}</span>
      </div>

      {/* Row 4: Fault chips + system label */}
      <div style={{ display:"flex", alignItems:"center", gap:5, marginBottom:8, flexWrap:"wrap" }}>
        {(t.fault_codes||[]).slice(0,4).map(c => <FaultChip key={c} code={c}/>)}
        {systems && <span style={{ fontSize:11, fontWeight:600, color:T.gray2 }}>{systems}</span>}
      </div>

      {/* Row 5: SLA + derate */}
      <div style={{ display:"flex", alignItems:"center", gap:8 }}>
        <span style={{ width:7, height:7, borderRadius:"50%", background:T.red, flexShrink:0, display:"inline-block" }}/>
        <span style={{ fontSize:11, fontWeight:700, color:T.gray1 }}>SLA: {t.sla_label || "—"}</span>
        {(t.derate_active || isHigh) && (
          <span style={{ fontSize:10, fontWeight:700, color:T.red, background:T.redBg, padding:"1px 6px", borderRadius:3, letterSpacing:0.3 }}>DERATE ACTIVE</span>
        )}
        <span style={{ marginLeft:"auto", color:T.gray3 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </span>
      </div>
    </button>
  );
}

// ─── TSB RESOLVER ─────────────────────────────────────────────────────────────
// Runtime fault code map — populated from /api/fault_codes on startup
let FAULT_SYSTEM_MAP = {};

// Maps system names (from fault_codes.json) to manual filenames
const SYSTEM_TO_MANUAL = {
  "Aftertreatment": "DEF_Aftertreatment_System.txt",
  "EGR":            "EGR_System.txt",
  "Fuel System":    "Fuel_System.txt",
  "Cooling":        "Cooling_System.txt",
  "Turbocharger":   "Turbocharger_System.txt",
  "Engine Protection": "DEF_Aftertreatment_System.txt",
  "Air Intake":     "Air_Intake_System.txt",
  "Lubrication":    "Lubrication_System.txt",
};
function resolveTSB(ref) {
  if (!ref) return null;
  // Try to match a system keyword in the ref string
  const systemMatch = Object.keys(SYSTEM_TO_MANUAL).find(s => ref.toUpperCase().includes(s.toUpperCase()));
  if (systemMatch) return { file: SYSTEM_TO_MANUAL[systemMatch], chunk: ref };
  // Fallback: default to DEF manual
  return { file: "DEF_Aftertreatment_System.txt", chunk: ref };
}

// ─── APPROVER PICKER ──────────────────────────────────────────────────────────
function ApproverPicker({ value, onChange }) {
  const [managers, setManagers] = useState([]);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    apiListManagers()
      .then(d => setManagers(d.managers || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ fontSize:12, color:T.gray3, padding:"10px 0" }}>Loading approvers…</div>;

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
      {managers.map(m => (
        <button key={m.manager_id} onClick={() => onChange(m)}
          style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"10px 12px", borderRadius:6,
            border:`1.5px solid ${value?.manager_id===m.manager_id ? T.black : T.border}`,
            background: value?.manager_id===m.manager_id ? T.black : T.white,
            cursor:"pointer", textAlign:"left", fontFamily:"inherit" }}>
          <div>
            <div style={{ fontSize:12, fontWeight:700, color: value?.manager_id===m.manager_id ? T.white : T.gray1 }}>{m.name}</div>
            <div style={{ fontSize:10, color: value?.manager_id===m.manager_id ? T.gray4 : T.gray3 }}>{m.role} · {m.depot}</div>
          </div>
          <div style={{ fontSize:10, fontWeight:700, color: value?.manager_id===m.manager_id ? T.gray4 : T.gray3 }}>{m.manager_id}</div>
        </button>
      ))}
    </div>
  );
}

// ─── UNSAFE ESCALATION MODAL ──────────────────────────────────────────────────
function UnsafeEscalationModal({ ticket, onClose, onSuccess }) {
  const [what, setWhat]         = useState("");
  const [approver, setApprover] = useState(null);
  const [confirming, setConfirm]= useState(false);
  const [loading, setLoading]   = useState(false);
  const [err, setErr]           = useState("");

  const submit = async () => {
    if (!what.trim()||!approver) { setErr("All fields required."); return; }
    setLoading(true);
    try {
      await apiEscalate(ticket.ticket_id, {
        escalation_type:"unsafe", reason:what.trim(),
        approver_id:approver.manager_id, approver_name:approver.name,
      });
      onSuccess();
    } catch { setErr("Failed to escalate. Check backend."); }
    finally { setLoading(false); }
  };

  return (
    <>
      <div onClick={onClose} style={{ position:"absolute", inset:0, background:"rgba(0,0,0,0.7)", zIndex:300 }}/>
      <div style={{ position:"absolute", bottom:0, left:0, right:0, zIndex:301, background:T.white, borderRadius:"20px 20px 0 0", padding:"24px 20px 32px" }}>
        <div style={{ display:"flex", justifyContent:"center", marginBottom:16 }}>
          <div style={{ background:T.red, borderRadius:8, padding:"6px 12px" }}>
            <span style={{ fontSize:12, fontWeight:800, color:T.white, letterSpacing:1 }}>⚠ UNSAFE — SAFETY STOP</span>
          </div>
        </div>
        {!confirming ? (
          <>
            <div style={{ fontSize:12, color:T.gray2, marginBottom:16, textAlign:"center", lineHeight:1.6 }}>
              This will immediately stop the job and notify your supervisor.
            </div>
            <div style={{ marginBottom:10 }}>
              <Label>WHAT DID YOU SEE? *</Label>
              <textarea value={what} onChange={e=>setWhat(e.target.value)} placeholder="Describe the hazard…" rows={3}
                style={{ width:"100%", padding:"10px 12px", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, resize:"none", outline:"none" }}/>
            </div>
            <div style={{ marginBottom:14 }}>
              <Label>SELECT APPROVER *</Label>
              <ApproverPicker value={approver} onChange={setApprover}/>
            </div>
            {err && <div style={{ fontSize:12, color:T.red, marginBottom:10 }}>{err}</div>}
            <button onClick={() => { if(!what.trim()||!approver){setErr("All fields required.");return;} setConfirm(true); setErr(""); }}
              style={{ width:"100%", padding:14, background:T.red, color:T.white, border:"none", borderRadius:6, fontSize:13, fontWeight:800, cursor:"pointer" }}>
              REVIEW & CONFIRM
            </button>
            <button onClick={onClose} style={{ width:"100%", padding:12, background:"none", color:T.gray2, border:"none", fontSize:13, cursor:"pointer", marginTop:6 }}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <div style={{ background:T.redBg, border:`1px solid ${T.redBorder}`, borderRadius:8, padding:"12px 14px", marginBottom:16 }}>
              <div style={{ fontSize:11, fontWeight:700, color:T.red, marginBottom:6 }}>Are you sure? This will immediately stop the job.</div>
              <div style={{ fontSize:12, color:T.gray1 }}><strong>Hazard:</strong> {what}</div>
              <div style={{ fontSize:12, color:T.gray1 }}><strong>Approver:</strong> {approver?.name} ({approver?.manager_id})</div>
            </div>
            <button onClick={submit} disabled={loading}
              style={{ width:"100%", padding:14, background:loading?"#ccc":T.red, color:T.white, border:"none", borderRadius:6, fontSize:13, fontWeight:800, cursor:loading?"default":"pointer" }}>
              {loading ? "STOPPING JOB…" : "STOP JOB & ESCALATE"}
            </button>
            <button onClick={() => setConfirm(false)} style={{ width:"100%", padding:12, background:"none", color:T.gray2, border:"none", fontSize:13, cursor:"pointer", marginTop:6 }}>
              Go back
            </button>
          </>
        )}
      </div>
    </>
  );
}

// ─── CHAT TAB (inline, full-height tab) ───────────────────────────────────────
function ChatTab({ ticket, currentUser, chatCache, setChatCache }) {
  const [messages, setMessages]       = useState(chatCache?.[ticket.ticket_id] || []);
  const [input, setInput]             = useState("");
  const [lang, setLang]               = useState("en");
  const [loading, setLoading]         = useState(false);
  const [pendingFile, setPendingFile] = useState(null);
  const [docViewer, setDocViewer]     = useState(null);
  const bottomRef = useRef(null);
  const cameraRef = useRef(null);
  const attachRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:"smooth" }); }, [messages]);
  useEffect(() => {
    if (setChatCache && messages.length > 0)
      setChatCache(prev => ({ ...prev, [ticket.ticket_id]: messages }));
  }, [messages]);

  const uploadFile = async (file) => {
    const fd = new FormData(); fd.append("file", file); fd.append("context","chat");
    try {
      const r = await fetch(`${API}/api/upload/${ticket.ticket_id}`, { method:"POST", body:fd });
      if (!r.ok) throw new Error();
      const d = await r.json(); return d.file_id;
    } catch { return null; }
  };

  const handleFilePicked = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    const isImage = file.type.startsWith("image/");
    const localUrl = isImage ? URL.createObjectURL(file) : null;
    const file_id = await uploadFile(file);
    setPendingFile({ url:localUrl, file_id, type:isImage?"image":"doc", name:file.name });
    e.target.value = "";
  };

  const sendSuggestion = useCallback((text) => {
    if (loading) return;
    setMessages([{ role:"user", text, image:null, sources:[] }]);
    setLoading(true);
    fetch(`${API}/api/chat`, { method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ ticket_id:ticket.ticket_id, message:text, language:lang, file_ids:[] }) })
    .then(r=>r.ok?r.json():null).then(d => {
      if (!d) throw new Error();
      setMessages(m=>[...m,{ role:"assistant", text:d.response?.answer??d.response?.message??JSON.stringify(d.response), sources:d.response?.sources||[] }]);
    }).catch(()=>setMessages(m=>[...m,{ role:"assistant", text:"Could not reach backend.", sources:[] }]))
    .finally(()=>setLoading(false));
  }, [loading, lang, ticket.ticket_id]);

  const send = useCallback(async () => {
    const q = input.trim(); const hasFile = !!pendingFile;
    if ((!q && !hasFile) || loading) return;
    const userText = q || "What can you see in this image?";
    setInput(""); setMessages(m=>[...m,{ role:"user", text:userText, image:pendingFile?.url||null, sources:[] }]);
    const pf = pendingFile; setPendingFile(null); setLoading(true);
    try {
      const r = await fetch(`${API}/api/chat`, { method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ ticket_id:ticket.ticket_id, message:userText, language:lang, file_ids:pf?.file_id?[pf.file_id]:[] }) });
      if (!r.ok) throw new Error();
      const d = await r.json();
      setMessages(m=>[...m,{ role:"assistant", text:d.response?.answer??d.response?.message??JSON.stringify(d.response), sources:d.response?.sources||[] }]);
    } catch { setMessages(m=>[...m,{ role:"assistant", text:"Could not reach backend.", sources:[] }]); }
    finally { setLoading(false); }
  }, [input, loading, lang, ticket.ticket_id, pendingFile]);

  const userInitial = currentUser?.name?.[0]?.toUpperCase() || "T";
  const SUGGESTIONS = [
    "DEF sensor resistance spec for X15?",
    "How do I diagnose fault code 3714?",
    "Step-by-step DEF system test procedure",
    "Any TSBs for DEF sensor failure on X15?",
  ];

  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%" }}>
      {/* Sub-header */}
      <div style={{ background:T.white, padding:"9px 14px 8px", borderBottom:`1px solid ${T.border}`, flexShrink:0, display:"flex", alignItems:"center", justifyContent:"space-between" }}>
        <div style={{ fontSize:12, color:T.gray2, lineHeight:1.4 }}>Fault codes &amp; manuals loaded for this ticket</div>
        <div style={{ display:"flex", background:T.bgPage, borderRadius:16, overflow:"hidden", border:`1px solid ${T.border}` }}>
          {["en","es"].map(l=>(
            <button key={l} onClick={()=>setLang(l)} style={{ padding:"3px 10px", fontSize:11, fontWeight:700, border:"none", cursor:"pointer", background:lang===l?T.black:"transparent", color:lang===l?T.white:T.gray2, borderRadius:14 }}>{l.toUpperCase()}</button>
          ))}
        </div>
      </div>

      {/* Messages or welcome */}
      {messages.length===0 && !loading ? (
        <div style={{ flex:1, overflowY:"auto", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:"0 18px 16px", gap:20 }}>
          <div style={{ width:52, height:52, borderRadius:14, background:T.black, display:"flex", alignItems:"center", justifyContent:"center" }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.5"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/><path d="M8 12h8M12 8v8" strokeWidth="1.8"/><circle cx="12" cy="12" r="2" fill="#fff" stroke="none"/></svg>
          </div>
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:15, fontWeight:800, color:T.black, marginBottom:4 }}>How can I help?</div>
            <div style={{ fontSize:11, color:T.gray3, lineHeight:1.6 }}>Ask about fault codes, test procedures, or send a photo.</div>
          </div>
          <div style={{ width:"100%", display:"flex", flexDirection:"column", gap:6 }}>
            {SUGGESTIONS.map((s,i)=>(
              <button key={i} onClick={()=>sendSuggestion(s)}
                style={{ width:"100%", padding:"10px 13px", background:T.white, border:`1px solid ${T.border}`, borderRadius:10, display:"flex", alignItems:"center", justifyContent:"space-between", cursor:"pointer", fontFamily:"inherit" }}>
                <span style={{ fontSize:12, color:T.gray1, textAlign:"left", lineHeight:1.4, flex:1 }}>{s}</span>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={T.gray4} strokeWidth="2.5"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ flex:1, overflowY:"auto", padding:"12px 14px", background:T.bgPage, display:"flex", flexDirection:"column", gap:10 }}>
          {messages.map((m,i)=>{
            const isUser = m.role==="user"; const hasRAG = !isUser && m.sources?.length>0;
            if (isUser) return (
              <div key={i} style={{ display:"flex", justifyContent:"flex-end", alignItems:"flex-end", gap:8 }}>
                <div style={{ maxWidth:"76%", display:"flex", flexDirection:"column", gap:4 }}>
                  {m.image && <img src={m.image} alt="attached" style={{ width:"100%", borderRadius:12, objectFit:"cover", maxHeight:140 }}/>}
                  <div style={{ padding:"10px 13px", borderRadius:"16px 16px 4px 16px", background:T.black, color:T.white, fontSize:13, lineHeight:1.6 }}>{m.text}</div>
                </div>
                <div style={{ width:28, height:28, borderRadius:"50%", background:T.red, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0, fontSize:12, fontWeight:700, color:T.white }}>{userInitial}</div>
              </div>
            );
            return (
              <div key={i} style={{ display:"flex", alignItems:"flex-start", gap:8 }}>
                <div style={{ width:28, height:28, borderRadius:"50%", background:T.red, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0, marginTop:2 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><circle cx="12" cy="12" r="3" fill="#fff" stroke="none"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12M5.64 18.36l2.12-2.12M16.24 7.76l2.12-2.12"/></svg>
                </div>
                <div style={{ maxWidth:"84%", display:"flex", flexDirection:"column" }}>
                  <div style={{ padding:"10px 13px", borderRadius:hasRAG?"16px 16px 0 4px":"16px 16px 16px 4px", background:T.white, color:T.gray1, fontSize:13, lineHeight:1.7, boxShadow:"0 1px 3px rgba(0,0,0,0.06)", borderLeft:`3px solid ${T.red}` }}>{m.text}</div>
                  {hasRAG && (
                    <div style={{ background:T.white, borderRadius:"0 0 16px 4px", padding:"7px 10px", display:"flex", gap:5, flexWrap:"wrap", boxShadow:"0 1px 3px rgba(0,0,0,0.06)" }}>
                      <span style={{ fontSize:9, fontWeight:700, color:T.red, letterSpacing:0.8 }}>FROM</span>
                      {m.sources.filter((s,i,arr)=>arr.findIndex(x=>x.source===s.source)===i).map((s,si)=>(
                        <button key={si} onClick={()=>setDocViewer(s)} style={{ display:"flex", alignItems:"center", gap:4, padding:"3px 9px", borderRadius:6, border:`1px solid ${T.border}`, background:T.white, color:T.gray1, fontSize:11, fontWeight:600, cursor:"pointer" }}>
                          <svg width="9" height="10" viewBox="0 0 24 24" fill="none" stroke={T.gray2} strokeWidth="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                          {(s.source||"").replace(/_/g," ").replace(".txt","").split(" ").slice(0,3).join(" ")}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {loading && (
            <div style={{ display:"flex", alignItems:"flex-start", gap:8 }}>
              <div style={{ width:28, height:28, borderRadius:"50%", background:T.red, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><circle cx="12" cy="12" r="3" fill="#fff" stroke="none"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12M5.64 18.36l2.12-2.12M16.24 7.76l2.12-2.12"/></svg>
              </div>
              <div style={{ padding:"10px 14px", background:T.white, borderRadius:"16px 16px 16px 4px", display:"flex", gap:6 }}>
                {[0,1,2].map(d=><span key={d} style={{ width:6,height:6,borderRadius:"50%",background:T.border,display:"block",animation:"pulse 1s infinite",animationDelay:`${d*0.2}s` }}/>)}
              </div>
            </div>
          )}
          <div ref={bottomRef}/>
        </div>
      )}

      {/* Pending file preview */}
      {pendingFile && (
        <div style={{ background:T.white, borderTop:`1px solid ${T.border}`, padding:"8px 12px", display:"flex", alignItems:"center", gap:10, flexShrink:0 }}>
          {pendingFile.type==="image"&&pendingFile.url
            ? <img src={pendingFile.url} alt="preview" style={{ width:44,height:44,borderRadius:6,objectFit:"cover" }}/>
            : <div style={{ width:44,height:44,borderRadius:6,background:T.blueBg,display:"flex",alignItems:"center",justifyContent:"center" }}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={T.blue} strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>}
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:11, fontWeight:700, color:T.gray1 }}>{pendingFile.type==="doc"?"Document":"Photo"} ready</div>
            <div style={{ fontSize:10, color:T.gray3, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{pendingFile.name}</div>
          </div>
          <button onClick={()=>setPendingFile(null)} style={{ background:"none",border:"none",cursor:"pointer",color:T.gray3,fontSize:20 }}>×</button>
        </div>
      )}

      <input ref={cameraRef} type="file" accept="image/*" capture="environment" onChange={handleFilePicked} style={{ display:"none" }}/>
      <input ref={attachRef} type="file" accept="image/*,.pdf,.doc,.docx,.txt,.csv" onChange={handleFilePicked} style={{ display:"none" }}/>

      {/* Input bar */}
      <div style={{ background:T.white, borderTop:`1px solid ${T.border}`, padding:"10px 12px", display:"flex", gap:8, alignItems:"center", flexShrink:0 }}>
        <button onClick={()=>cameraRef.current?.click()} style={{ width:36,height:36,borderRadius:"50%",background:T.bgPage,border:`1px solid ${T.border}`,cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={T.gray2} strokeWidth="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
        </button>
        <button onClick={()=>attachRef.current?.click()} style={{ width:36,height:36,borderRadius:"50%",background:T.black,border:"none",cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&send()}
          placeholder="Ask about this fault…"
          style={{ flex:1,padding:"10px 14px",border:`1px solid ${T.border}`,borderRadius:24,fontSize:13,outline:"none",background:T.bgPage,color:T.black }}/>
        <button onClick={send} style={{ width:36,height:36,borderRadius:"50%",background:(input.trim()||pendingFile)?T.red:"#ccc",border:"none",cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={T.white} strokeWidth="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
      <div style={{ background:T.white, padding:"4px 0 6px", textAlign:"center", borderTop:`1px solid ${T.borderLight}` }}>
        <span style={{ fontSize:10, color:T.gray4 }}>AI can make mistakes. Please double-check information.</span>
      </div>

      {docViewer && <DocViewer source={docViewer} onClose={()=>setDocViewer(null)}/>}
    </div>
  );
}

// ─── CHAT DRAWER ──────────────────────────────────────────────────────────────
function ChatDrawer({ ticket, currentUser, chatCache, setChatCache, onClose }) {
  const [messages, setMessages]       = useState(chatCache?.[ticket.ticket_id] || []);
  const [input, setInput]             = useState("");
  const [lang, setLang]               = useState("en");
  const [loading, setLoading]         = useState(false);
  const [pendingFile, setPendingFile] = useState(null);
  const [docViewer, setDocViewer]     = useState(null);
  const bottomRef  = useRef(null);
  const cameraRef  = useRef(null);
  const attachRef  = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:"smooth" }); }, [messages]);
  useEffect(() => {
    if (setChatCache && messages.length > 0)
      setChatCache(prev => ({ ...prev, [ticket.ticket_id]: messages }));
  }, [messages]);

  const uploadFile = async (file) => {
    const fd = new FormData(); fd.append("file", file); fd.append("context","chat");
    try {
      const r = await fetch(`${API}/api/upload/${ticket.ticket_id}`, { method:"POST", body:fd });
      if (!r.ok) throw new Error();
      const d = await r.json(); return d.file_id;
    } catch { return null; }
  };

  const handleFilePicked = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    const isImage = file.type.startsWith("image/");
    const localUrl = isImage ? URL.createObjectURL(file) : null;
    const file_id = await uploadFile(file);
    setPendingFile({ url:localUrl, file_id, type:isImage?"image":"doc", name:file.name });
    e.target.value = "";
  };

  const sendSuggestion = useCallback((text) => {
    if (loading) return;
    setMessages([{ role:"user", text, image:null, sources:[] }]);
    setLoading(true);
    fetch(`${API}/api/chat`, { method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ ticket_id:ticket.ticket_id, message:text, language:lang, file_ids:[] }),
    })
    .then(r=>r.ok?r.json():null).then(d => {
      if (!d) throw new Error();
      setMessages(m=>[...m,{ role:"assistant", text:d.response?.answer??d.response?.message??JSON.stringify(d.response), sources:d.response?.sources||[] }]);
    }).catch(()=>setMessages(m=>[...m,{ role:"assistant", text:"Could not reach backend.", sources:[] }]))
    .finally(()=>setLoading(false));
  }, [loading, lang, ticket.ticket_id]);

  const send = useCallback(async () => {
    const q = input.trim(); const hasFile = !!pendingFile;
    if ((!q && !hasFile) || loading) return;
    const userText = q || "What can you see in this image?";
    setInput(""); setMessages(m=>[...m,{ role:"user", text:userText, image:pendingFile?.url||null, sources:[] }]);
    const pf = pendingFile; setPendingFile(null); setLoading(true);
    try {
      const r = await fetch(`${API}/api/chat`, { method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ ticket_id:ticket.ticket_id, message:userText, language:lang, file_ids:pf?.file_id?[pf.file_id]:[] }) });
      if (!r.ok) throw new Error();
      const d = await r.json();
      setMessages(m=>[...m,{ role:"assistant", text:d.response?.answer??d.response?.message??JSON.stringify(d.response), sources:d.response?.sources||[] }]);
    } catch { setMessages(m=>[...m,{ role:"assistant", text:"Could not reach backend.", sources:[] }]); }
    finally { setLoading(false); }
  }, [input, loading, lang, ticket.ticket_id, pendingFile]);

  const userInitial = currentUser?.name?.[0]?.toUpperCase() || "T";
  const SUGGESTIONS = ["DEF sensor resistance spec for X15?","How do I diagnose fault code 3714?","Step-by-step DEF system test procedure","Any TSBs for DEF sensor failure on X15?"];

  return (
    <>
      <div onClick={onClose} style={{ position:"absolute", inset:0, background:"rgba(0,0,0,0.4)", zIndex:200 }}/>
      <div style={{ position:"absolute", bottom:0, left:0, right:0, top:"8%", zIndex:201, background:T.white, borderRadius:"20px 20px 0 0", display:"flex", flexDirection:"column", animation:"slidein 0.3s ease" }}>
        {/* Handle + header */}
        <div style={{ flexShrink:0 }}>
          <div style={{ display:"flex", justifyContent:"center", padding:"10px 0 0" }}>
            <div style={{ width:32, height:3, borderRadius:2, background:T.border }}/>
          </div>
          <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"10px 16px 8px", borderBottom:`1px solid ${T.border}` }}>
            <div style={{ display:"flex", alignItems:"center", gap:8 }}>
              <div style={{ width:28, height:28, borderRadius:8, background:T.black, display:"flex", alignItems:"center", justifyContent:"center" }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><circle cx="12" cy="12" r="3" fill="#fff" stroke="none"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12M5.64 18.36l2.12-2.12M16.24 7.76l2.12-2.12"/></svg>
              </div>
              <div>
                <div style={{ fontSize:13, fontWeight:800, color:T.black }}>AI Assistant</div>
                <div style={{ fontSize:10, color:T.gray3 }}>Fault codes & manuals loaded</div>
              </div>
            </div>
            <div style={{ display:"flex", alignItems:"center", gap:8 }}>
              <div style={{ display:"flex", background:T.bgPage, borderRadius:16, overflow:"hidden", border:`1px solid ${T.border}` }}>
                {["en","es"].map(l=>(
                  <button key={l} onClick={()=>setLang(l)} style={{ padding:"3px 10px", fontSize:11, fontWeight:700, border:"none", cursor:"pointer", background:lang===l?T.black:"transparent", color:lang===l?T.white:T.gray2, borderRadius:14 }}>{l.toUpperCase()}</button>
                ))}
              </div>
              <button onClick={onClose} style={{ width:28, height:28, borderRadius:"50%", background:T.bgPage, border:`1px solid ${T.border}`, cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center" }}>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={T.gray2} strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>
        </div>

        {/* Messages */}
        {messages.length===0 && !loading ? (
          <div style={{ flex:1, overflowY:"auto", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:"0 18px 16px", gap:20 }}>
            <div style={{ textAlign:"center" }}>
              <div style={{ fontSize:15, fontWeight:800, color:T.black, marginBottom:4 }}>How can I help?</div>
              <div style={{ fontSize:11, color:T.gray3, lineHeight:1.6 }}>Ask about fault codes, procedures, or send a photo.</div>
            </div>
            <div style={{ width:"100%", display:"flex", flexDirection:"column", gap:6 }}>
              {SUGGESTIONS.map((s,i)=>(
                <button key={i} onClick={()=>sendSuggestion(s)}
                  style={{ width:"100%", padding:"10px 13px", background:T.white, border:`1px solid ${T.border}`, borderRadius:10, display:"flex", alignItems:"center", justifyContent:"space-between", cursor:"pointer", fontFamily:"inherit" }}>
                  <span style={{ fontSize:12, color:T.gray1, textAlign:"left", lineHeight:1.4, flex:1 }}>{s}</span>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={T.gray4} strokeWidth="2.5"><polyline points="9 18 15 12 9 6"/></svg>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ flex:1, overflowY:"auto", padding:"12px 14px", background:T.bgPage, display:"flex", flexDirection:"column", gap:10 }}>
            {messages.map((m,i)=>{
              const isUser = m.role==="user"; const hasRAG = !isUser && m.sources?.length>0;
              if (isUser) return (
                <div key={i} style={{ display:"flex", justifyContent:"flex-end", alignItems:"flex-end", gap:8 }}>
                  <div style={{ maxWidth:"76%", display:"flex", flexDirection:"column", gap:4 }}>
                    {m.image && <img src={m.image} alt="attached" style={{ width:"100%", borderRadius:12, objectFit:"cover", maxHeight:140 }}/>}
                    <div style={{ padding:"10px 13px", borderRadius:"16px 16px 4px 16px", background:T.black, color:T.white, fontSize:13, lineHeight:1.6 }}>{m.text}</div>
                  </div>
                  <div style={{ width:28, height:28, borderRadius:"50%", background:T.red, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0, fontSize:12, fontWeight:700, color:T.white }}>{userInitial}</div>
                </div>
              );
              return (
                <div key={i} style={{ display:"flex", alignItems:"flex-start", gap:8 }}>
                  <div style={{ width:28, height:28, borderRadius:"50%", background:T.red, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0, marginTop:2 }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><circle cx="12" cy="12" r="3" fill="#fff" stroke="none"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12M5.64 18.36l2.12-2.12M16.24 7.76l2.12-2.12"/></svg>
                  </div>
                  <div style={{ maxWidth:"84%", display:"flex", flexDirection:"column" }}>
                    <div style={{ padding:"10px 13px", borderRadius:hasRAG?"16px 16px 0 4px":"16px 16px 16px 4px", background:T.white, color:T.gray1, fontSize:13, lineHeight:1.7, boxShadow:"0 1px 3px rgba(0,0,0,0.06)", borderLeft:`3px solid ${T.red}` }}>{m.text}</div>
                    {hasRAG && (
                      <div style={{ background:T.white, borderRadius:"0 0 16px 4px", padding:"7px 10px", display:"flex", gap:5, flexWrap:"wrap", boxShadow:"0 1px 3px rgba(0,0,0,0.06)" }}>
                        <span style={{ fontSize:9, fontWeight:700, color:T.red, letterSpacing:0.8 }}>FROM</span>
                        {m.sources.filter((s,i,arr)=>arr.findIndex(x=>x.source===s.source)===i).map((s,si)=>(
                          <button key={si} onClick={()=>setDocViewer(s)} style={{ display:"flex", alignItems:"center", gap:4, padding:"3px 9px", borderRadius:6, border:`1px solid ${T.border}`, background:T.white, color:T.gray1, fontSize:11, fontWeight:600, cursor:"pointer" }}>
                            <svg width="9" height="10" viewBox="0 0 24 24" fill="none" stroke={T.gray2} strokeWidth="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                            {(s.source||"").replace(/_/g," ").replace(".txt","").split(" ").slice(0,3).join(" ")}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            {loading && (
              <div style={{ display:"flex", alignItems:"flex-start", gap:8 }}>
                <div style={{ width:28, height:28, borderRadius:"50%", background:T.red, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><circle cx="12" cy="12" r="3" fill="#fff" stroke="none"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12M5.64 18.36l2.12-2.12M16.24 7.76l2.12-2.12"/></svg>
                </div>
                <div style={{ padding:"10px 14px", background:T.white, borderRadius:"16px 16px 16px 4px", display:"flex", gap:6 }}>
                  {[0,1,2].map(d=><span key={d} style={{ width:6,height:6,borderRadius:"50%",background:T.border,display:"block",animation:"pulse 1s infinite",animationDelay:`${d*0.2}s` }}/>)}
                </div>
              </div>
            )}
            <div ref={bottomRef}/>
          </div>
        )}

        {/* Pending file */}
        {pendingFile && (
          <div style={{ background:T.white, borderTop:`1px solid ${T.border}`, padding:"8px 12px", display:"flex", alignItems:"center", gap:10, flexShrink:0 }}>
            {pendingFile.type==="image"&&pendingFile.url
              ? <img src={pendingFile.url} alt="preview" style={{ width:44,height:44,borderRadius:6,objectFit:"cover" }}/>
              : <div style={{ width:44,height:44,borderRadius:6,background:T.blueBg,display:"flex",alignItems:"center",justifyContent:"center" }}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={T.blue} strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>}
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ fontSize:11, fontWeight:700, color:T.gray1 }}>{pendingFile.type==="doc"?"Document":"Photo"} ready</div>
              <div style={{ fontSize:10, color:T.gray3, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{pendingFile.name}</div>
            </div>
            <button onClick={()=>setPendingFile(null)} style={{ background:"none",border:"none",cursor:"pointer",color:T.gray3,fontSize:20 }}>×</button>
          </div>
        )}

        <input ref={cameraRef} type="file" accept="image/*" capture="environment" onChange={handleFilePicked} style={{ display:"none" }}/>
        <input ref={attachRef} type="file" accept="image/*,.pdf,.doc,.docx,.txt,.csv" onChange={handleFilePicked} style={{ display:"none" }}/>

        {/* Input bar */}
        <div style={{ background:T.white, borderTop:`1px solid ${T.border}`, padding:"10px 12px", display:"flex", gap:8, alignItems:"center", flexShrink:0 }}>
          <button onClick={()=>cameraRef.current?.click()} style={{ width:36,height:36,borderRadius:"50%",background:T.bgPage,border:`1px solid ${T.border}`,cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={T.gray2} strokeWidth="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
          </button>
          <button onClick={()=>attachRef.current?.click()} style={{ width:36,height:36,borderRadius:"50%",background:T.black,border:"none",cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
          <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&send()}
            placeholder="Ask about this fault…"
            style={{ flex:1,padding:"10px 14px",border:`1px solid ${T.border}`,borderRadius:24,fontSize:13,outline:"none",background:T.bgPage,color:T.black }}/>
          <button onClick={send} style={{ width:36,height:36,borderRadius:"50%",background:(input.trim()||pendingFile)?T.red:"#ccc",border:"none",cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={T.white} strokeWidth="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          </button>
        </div>
        <div style={{ background:T.white, padding:"4px 0 6px", textAlign:"center" }}>
          <span style={{ fontSize:10, color:T.gray4 }}>AI can make mistakes. Please double-check information.</span>
        </div>
        {docViewer && <DocViewer source={docViewer} onClose={()=>setDocViewer(null)}/>}
      </div>
    </>
  );
}

// ─── TICKET DETAIL ────────────────────────────────────────────────────────────
function TicketDetail({ ticket, currentUser, triageCache, setTriageCache, chatCache, setChatCache }) {
  const [tab, setTab]             = useState("triage");
  const [unsafeOpen, setUnsafe]   = useState(false);
  const [escalated, setEscalated] = useState(false);
  const [rcaDone, setRcaDone]     = useState(false);
  const [goToAction, setGoAction] = useState(false);
  const [triageDoc, setTriageDoc] = useState(null);  // lifted here so DocViewer covers full phone shell

  useEffect(() => { if (goToAction) { setTab("action"); setGoAction(false); } }, [goToAction]);

  // TRIAGE → CHAT → RCA → ACTION
  const tabs = [
    { id:"triage", label:"TRIAGE",
      icon:<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> },
    { id:"chat",   label:"CHAT",
      icon:<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> },
    { id:"rca",    label:"RCA",
      icon:<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> },
    { id:"action", label:"ACTION",
      icon:<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg> },
  ];

  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%", position:"relative" }}>
      {/* Header */}
      <div style={{ background:T.charcoal, color:T.white, flexShrink:0 }}>
        {/* Top row: consistent hamburger | CUMMINS | bell */}
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"12px 16px 0" }}>
          <button style={{ background:"none", border:"none", color:T.white, cursor:"pointer", padding:0 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
          <span style={{ fontSize:14, fontWeight:900, letterSpacing:2.5 }}>CUMMINS</span>
          <button style={{ background:"none", border:"none", color:T.white, cursor:"pointer", padding:0 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
          </button>
        </div>

        {/* Ticket identity row: ID + customer name | priority + unsafe */}
        <div style={{ display:"flex", alignItems:"flex-end", justifyContent:"space-between", padding:"10px 14px 10px" }}>
          <div>
            <div style={{ fontSize:9, color:"#666", letterSpacing:0.8, marginBottom:3 }}>{ticket.ticket_id}</div>
            <div style={{ fontSize:16, fontWeight:900, color:T.white, lineHeight:1.2 }}>{ticket.customer}</div>
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:5, flexShrink:0 }}>
            <div style={{ background:ticket.priority==="High"||ticket.derate_active?T.red:T.amber,
              color:T.white, fontSize:10, fontWeight:800, padding:"3px 9px", borderRadius:4, letterSpacing:0.8 }}>
              {ticket.priority==="High"||ticket.derate_active?"High":"Medium"}
            </div>
            {!escalated ? (
              <button onClick={() => setUnsafe(true)}
                style={{ background:"transparent", border:`1px solid #555`, borderRadius:4, padding:"3px 7px", cursor:"pointer", display:"flex", alignItems:"center", gap:3 }}>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#aaa" strokeWidth="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                <span style={{ fontSize:9, fontWeight:700, color:"#aaa", letterSpacing:0.5 }}>FLAG UNSAFE</span>
              </button>
            ) : (
              <div style={{ background:"rgba(211,47,47,0.15)", border:`1px solid ${T.red}`, borderRadius:4, padding:"3px 7px", display:"flex", alignItems:"center", gap:3 }}>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={T.red} strokeWidth="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                <span style={{ fontSize:9, fontWeight:800, color:T.red, letterSpacing:0.5 }}>UNSAFE</span>
              </div>
            )}
          </div>
        </div>

        {/* Tab bar */}
        <div style={{ display:"flex", borderTop:"1px solid #2a2a2a" }}>
          {tabs.map(tb => {
            const a      = tab===tb.id;
            const locked = tb.id==="action" && !rcaDone;
            return (
              <button key={tb.id} onClick={() => !locked && setTab(tb.id)}
                style={{
                  flex:1, padding:"9px 0", background:"none", border:"none",
                  color: a ? T.white : "#666",
                  fontSize:9, fontWeight:700,
                  cursor: locked ? "default" : "pointer",
                  letterSpacing:0.8,
                  borderBottom: a ? `2px solid ${T.red}` : "2px solid transparent",
                  display:"flex", alignItems:"center", justifyContent:"center", gap:3,
                  opacity: locked ? 0.35 : 1,
                }}>
                {tb.icon}{tb.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab content */}
      <div style={{ flex:1, overflowY:"auto", background:T.bgPage, position:"relative" }}>
        {tab==="triage" && <TriageTab ticket={ticket} onStartRCA={() => setTab("rca")} triageCache={triageCache} setTriageCache={setTriageCache} setTriageDoc={setTriageDoc}/>}
        {tab==="chat"   && <ChatTab ticket={ticket} currentUser={currentUser} chatCache={chatCache} setChatCache={setChatCache}/>}
        {tab==="rca"    && <RCATab ticket={ticket} currentUser={currentUser} onComplete={() => { setRcaDone(true); setGoAction(true); }}/>}
        {tab==="action" && <ActionTab ticket={ticket} currentUser={currentUser} rcaDone={rcaDone}/>}
      </div>

      {/* Unsafe modal */}
      {unsafeOpen && <UnsafeEscalationModal ticket={ticket} onClose={() => setUnsafe(false)} onSuccess={() => { setUnsafe(false); setEscalated(true); }}/>}

      {/* DocViewer at top level so it covers full phone shell */}
      {triageDoc && <DocViewer source={triageDoc} onClose={() => setTriageDoc(null)}/>}
    </div>
  );
}

// ─── DOC VIEWER ───────────────────────────────────────────────────────────────
function DocViewer({ source, onClose }) {
  const [docText, setDocText] = useState(null);
  const [loading, setLoading] = useState(true);
  const hiRef = useRef(null);

  useEffect(() => {
    fetch(`${API}/api/manual/${encodeURIComponent(source.source)}`)
      .then(r=>r.ok?r.json():null).then(d=>{setDocText(d?.content||null);setLoading(false);})
      .catch(()=>setLoading(false));
  }, [source.source]);

  useEffect(() => { if (!loading && hiRef.current) setTimeout(()=>hiRef.current?.scrollIntoView({behavior:"smooth",block:"center"}),200); }, [loading]);

  const segments = (text, chunk) => {
    if (!text||!chunk) return [{ t:text||"", hi:false }];
    const idx = text.indexOf(chunk.slice(0,60));
    if (idx===-1) return [{ t:text, hi:false }];
    const end = Math.min(idx+chunk.length, text.length);
    return [{ t:text.slice(0,idx), hi:false },{ t:text.slice(idx,end), hi:true },{ t:text.slice(end), hi:false }];
  };

  const label = source.source?.replace(/_/g," ").replace(".txt","") || "Document";

  return (
    <>
      <div onClick={onClose} style={{ position:"absolute", inset:0, background:"rgba(0,0,0,0.55)", zIndex:200, backdropFilter:"blur(4px)" }}/>
      <div style={{ position:"absolute", bottom:0, left:0, right:0, top:"6%", zIndex:201, background:"#FDFDFB", borderRadius:"20px 20px 0 0", boxShadow:"0 -16px 60px rgba(0,0,0,0.3)", display:"flex", flexDirection:"column", animation:"slidein 0.3s ease" }}>
        <div style={{ display:"flex", justifyContent:"center", padding:"10px 0 0", flexShrink:0 }}><div style={{ width:32, height:3, borderRadius:2, background:T.border }}/></div>
        <div style={{ padding:"8px 16px 12px", borderBottom:`1px solid ${T.border}`, flexShrink:0, background:T.white }}>
          <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:8 }}>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:9, fontWeight:700, color:T.gray3, letterSpacing:1.2, marginBottom:4 }}>SERVICE MANUAL</div>
              <div style={{ fontSize:14, fontWeight:800, color:T.black, lineHeight:1.3 }}>{label}</div>
              <div style={{ marginTop:7, display:"inline-flex", alignItems:"center", gap:5, padding:"3px 8px", background:"#FFF9C4", borderRadius:4 }}>
                <div style={{ width:7, height:7, borderRadius:1, background:"#F9A825" }}/><span style={{ fontSize:10, fontWeight:600, color:"#5D4037" }}>Retrieved section highlighted</span>
              </div>
            </div>
            <button onClick={onClose} style={{ width:28, height:28, borderRadius:"50%", background:T.bgPage, border:`1px solid ${T.border}`, cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0, marginTop:2 }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={T.gray2} strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>
        <div style={{ flex:1, overflowY:"auto", padding:16, overscrollBehavior:"contain" }}>
          {loading ? <div style={{ display:"flex", gap:8, padding:20, color:T.gray3, fontSize:13 }}>{[0,1,2].map(d=><span key={d} style={{ width:6,height:6,borderRadius:"50%",background:T.border,display:"block",animation:"pulse 1s infinite",animationDelay:`${d*0.2}s` }}/>)}<span>Loading…</span></div>
          : docText ? (
            <div style={{ fontFamily:"-apple-system,sans-serif", fontSize:13, lineHeight:1.8, color:"#222", whiteSpace:"pre-wrap", wordBreak:"break-word" }}>
              {segments(docText, source.chunk).map((seg,i)=>{
                if (!seg.hi) return seg.t.split("\n").map((line,li)=>{
                  const trimmed = line.trim();
                  if (!trimmed) return <div key={`${i}-${li}`} style={{ height:4 }}/>;
                  const isHeader = trimmed.match(/^[A-Z][A-Z\s\/\-–]{6,}$/) || trimmed.startsWith("===");
                  if (isHeader) return <div key={`${i}-${li}`} style={{ fontSize:11, fontWeight:800, color:"#888", letterSpacing:1, marginTop:18, marginBottom:4, textTransform:"uppercase" }}>{trimmed.replace(/^[=\-]+\s*/,"")}</div>;
                  return <div key={`${i}-${li}`} style={{ marginBottom:2 }}>{line}</div>;
                });
                return <mark key={i} ref={hiRef} style={{ background:"#FEF08A", borderRadius:3, padding:"2px 0" }}>{seg.t}</mark>;
              })}
            </div>
          ) : <div style={{ padding:20, fontSize:13, color:T.gray3, fontStyle:"italic" }}>Document not available — ensure backend is running.</div>}
        </div>
      </div>
    </>
  );
}

// ─── TRIAGE TAB ───────────────────────────────────────────────────────────────
function TriageTab({ ticket:t, onStartRCA, triageCache, setTriageCache, setTriageDoc }) {
  const cached = triageCache?.[t.ticket_id] || null;
  const [ai, setAi]           = useState(cached);
  const [loading, setLoading] = useState(false);

  const [showMoreEquip, setShowMoreEquip] = useState(false);
  const [showMoreFF, setShowMoreFF]       = useState(false);
  const [showMoreAI, setShowMoreAI]       = useState(false);

  const [autoSafety, setAutoSafety] = useState(cached?.safety || null);

  // Auto-fetch safety warnings instantly via dedicated endpoint (no LLM wait)
  useEffect(() => {
    if (cached?.safety || autoSafety) return;
    fetch(`${API}/api/safety/${t.ticket_id}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return;
        setAutoSafety(d.warnings || []);
      })
      .catch(() => {});
  }, [t.ticket_id]);

  const runDiagnosis = () => {
    if (loading || ai) return;
    setLoading(true);
    fetch(`${API}/api/triage`, { method:"POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ ticket_id:t.ticket_id, customer:t.customer, location:t.location, serial_number:t.serial_number, issue_description:t.issue_description, tech_id:t.tech_id }) })
    .then(r=>r.ok?r.json():null).then(d=>{
      if (!d) return;
      const tr = d.triage_results;
      const result = {
        priority:     tr?.severity?.priority||"P1",
        sla:          tr?.severity?.sla_hours||t.sla_label,
        impact:       tr?.severity?.impact||"",
        likely_cause: tr?.diagnosis?.narrative||"Unable to generate diagnosis.",
        confidence:   tr?.diagnosis?.evidence?.success_rate_pct??0,
        similar_cases:tr?.diagnosis?.evidence?.similar_cases_found??0,
        ref:          (tr?.diagnosis?.evidence?.tsb_references||[]).join(", "),
        resolution:   tr?.diagnosis?.evidence?.most_common_resolution||"",
        safety:       tr?.safety?.warnings||[],
        rec_parts:    (tr?.resources?.parts||[]).map(p=>`${p.description} (${p.part_number})`),
      };
      setAi(result);
      if (setTriageCache) setTriageCache(prev=>({...prev,[t.ticket_id]:result}));
    }).catch(()=>{}).finally(()=>setLoading(false));
  };
  const isShutdown = t.shutdown_active; const isDerate = t.derate_active!==false;
  const priorityRaw = ai?.priority||(isDerate?"P1":"P2");
  const priorityLabel = priorityRaw==="P1"||priorityRaw==="High"||priorityRaw==="1" ? "PRIORITY 1" : "PRIORITY 2";
  const slaHrs = ai?.sla?`${ai.sla}:00H`:t.sla_label;

  const Skeleton = ({ w="100%", h=14, mb=6 }) => (
    <div style={{ width:w, height:h, borderRadius:4, marginBottom:mb, background:"linear-gradient(90deg,#eee 25%,#f5f5f5 50%,#eee 75%)", backgroundSize:"200% 100%", animation:"shimmer 1.4s infinite" }}/>
  );

  return (
    <>
      <div style={{ paddingBottom:24 }}>
        <style>{`@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}`}</style>

        {/* Priority + SLA hero */}
        <Card>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:(isDerate||isShutdown)?12:0 }}>
            <div>
              <div style={{ fontSize:22, fontWeight:900, color:T.red, lineHeight:1 }}>{priorityLabel}</div>
              <div style={{ fontSize:10, color:T.gray3, fontWeight:700, marginTop:3, letterSpacing:0.8 }}>PRIORITY LEVEL</div>
            </div>
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:28, fontWeight:900, color:T.black, lineHeight:1 }}>{slaHrs}</div>
              <div style={{ fontSize:10, color:T.gray3, fontWeight:700, marginTop:3, letterSpacing:0.8 }}>SLA HRS</div>
            </div>
          </div>
          {(isDerate||isShutdown) && (
            <div style={{ background:T.red, borderRadius:5, padding:"7px 12px", display:"flex", alignItems:"center", gap:8 }}>
              <span style={{ width:8, height:8, borderRadius:"50%", background:"rgba(255,255,255,0.6)", flexShrink:0 }}/>
              <span style={{ fontSize:11, fontWeight:800, color:T.white, letterSpacing:0.8 }}>
                {isShutdown ? "ENGINE SHUTDOWN ACTIVE" : "DERATE ACTIVE · ENGINE LIMITED"}
              </span>
            </div>
          )}
        </Card>


        <Card><Label>EQUIPMENT</Label>
          {[
            ["CUSTOMER", t.customer],
            ["LOCATION", t.location],
            ["ENGINE",   t.equipment_model],
            ["HOURS",    `${(t.equipment_hours||0).toLocaleString()} hrs`, (t.equipment_hours||0)>15000?T.red:(t.equipment_hours||0)>8000?T.amber:null],
            ["WARRANTY", (t.warranty||(t.warranty_active?"Active":"Expired")), (t.warranty==="Active"||t.warranty_active)?T.green:T.red],
          ].map(([l,v,c])=><Row key={l} label={l} value={v} vc={c}/>)}
          {showMoreEquip && (<>
            {[
              ["SERIAL NO",  t.serial_number||"—"],
              ["TYPE",       t.equipment_type||"—"],
              ["CM VERSION", t.cm_version||"—"],
              ...(t.warranty_expiry?[["EXPIRY", new Date(t.warranty_expiry).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"})]]:[] ),
              ...(t.billable_to?[["BILLABLE TO", t.billable_to]]:[] ),
              ...(t.coverage_type?[["COVERAGE", t.coverage_type]]:[] ),
            ].map(([l,v,c])=><Row key={l} label={l} value={v} vc={c}/>)}
            {(t.fault_codes||[]).length>0 && (
              <div style={{marginTop:8,paddingTop:8,borderTop:`1px solid ${T.border}`}}>
                <div style={{fontSize:9,fontWeight:800,color:T.gray3,letterSpacing:1,marginBottom:6}}>ACTIVE FAULT CODES</div>
                {(t.fault_codes||[]).map(code=>(
                  <div key={code} style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>
                    <span style={{fontSize:11,fontWeight:800,color:T.red,fontFamily:"monospace"}}>{code}</span>
                    <span style={{fontSize:11,color:T.gray1,maxWidth:"60%",textAlign:"right"}}>{FAULT_SYSTEM_MAP[code]||"Unknown System"}</span>
                  </div>
                ))}
                {(t.inactive_codes||[]).length>0 && (
                  <div style={{marginTop:6,paddingTop:6,borderTop:`1px dashed ${T.border}`}}>
                    <div style={{fontSize:9,fontWeight:700,color:T.gray3,letterSpacing:0.8,marginBottom:4}}>INACTIVE / HISTORICAL</div>
                    {t.inactive_codes.map(code=>(
                      <div key={code} style={{display:"flex",justifyContent:"space-between",marginBottom:3}}>
                        <span style={{fontSize:11,fontWeight:700,color:T.gray3,fontFamily:"monospace"}}>{code}</span>
                        <span style={{fontSize:11,color:T.gray3,maxWidth:"60%",textAlign:"right"}}>{FAULT_SYSTEM_MAP[code]||"Unknown System"}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {t.issue_description && (
              <div style={{marginTop:8,paddingTop:8,borderTop:`1px solid ${T.border}`}}>
                <div style={{fontSize:9,fontWeight:800,color:T.gray3,letterSpacing:1,marginBottom:4}}>OPERATOR REPORT</div>
                <div style={{fontSize:12,color:T.gray1,lineHeight:1.6,fontStyle:"italic"}}>"{t.issue_description}"</div>
              </div>
            )}
          </>)}
          <button onClick={()=>setShowMoreEquip(p=>!p)} style={{marginTop:6,background:"none",border:"none",padding:"4px 0 2px",cursor:"pointer",fontSize:9,fontWeight:700,color:T.gray3,letterSpacing:0.8,display:"block",marginLeft:"auto",fontFamily:"inherit"}}>
            {showMoreEquip?"↑ SHOW LESS":"↓ SHOW MORE"}
          </button>
        </Card>

        <Card><Label>FREEZE FRAME <span style={{fontSize:9,fontWeight:600,color:T.gray3,letterSpacing:0}}></span></Label>
          {(()=>{
            const ff=t.freeze_frame||{};
            const defPct=ff.def_level_pct??null;
            const defLvl=ff.def_level||(defPct!=null?`${defPct}%`:"—");
            const defColor=defPct!=null?(defPct<10?T.red:defPct<25?T.amber:null):null;
            const rpm=ff.engine_rpm!=null?`${ff.engine_rpm.toLocaleString()}`:"—";
            const coolF=ff.coolant_temp_f??null;
            const temp=ff.coolant_temp||(coolF!=null?`${coolF}°F`:"—");
            const tempColor=coolF!=null?(coolF>=230?T.red:coolF>=215?T.amber:null):null;
            const oilPsi=ff.oil_pressure_psi??null;
            const oil=ff.oil_pressure||(oilPsi!=null?`${oilPsi} psi`:"—");
            const oilColor=oilPsi!=null?(oilPsi<20?T.red:oilPsi<30?T.amber:T.green):null;
            const dpf=ff.dpf_soot_load_pct??null;
            const dpfColor=dpf!=null?(dpf>=90?T.red:dpf>=70?T.amber:null):null;
            const boost=ff.boost_pressure_psi??null;
            const boostColor=boost!=null?(boost<15?T.red:boost<18?T.amber:null):null;
            const exhaust=ff.exhaust_temp_f??null;
            const exhaustColor=exhaust!=null?(exhaust>=1000?T.red:exhaust>=900?T.amber:null):null;
            const fuel=ff.fuel_pressure_kpa??null;
            const fuelColor=fuel!=null?(fuel<15?T.red:fuel<20?T.amber:null):null;
            const load=ff.load_pct??null;
            const always=[
              ["DEF LEVEL",   defLvl,                                        defColor],
              ["ENGINE RPM",  rpm,                                            null],
              ["COOLANT TEMP",temp,                                           tempColor],
              ["OIL PRESSURE",oil,                                            oilColor],
            ];
            const extra=[
              ["DPF SOOT",    dpf!=null?`${dpf}%`:"—",                 dpfColor],
              ["ENGINE LOAD", load!=null?`${load}%`:"—",                null],
              ["EXHAUST TEMP",exhaust!=null?`${exhaust}°F`:"—",    exhaustColor],
              ["BOOST PRESS", boost!=null?`${boost} psi`:"—",           boostColor],
              ["FUEL PRESS",  fuel!=null?`${fuel} kPa`:"—",             fuelColor],
            ];
            return (
              <>
                {always.map(([l,v,c])=><Row key={l} label={l} value={v} vc={c}/>)}
                {showMoreFF && extra.map(([l,v,c])=><Row key={l} label={l} value={v} vc={c}/>)}
                <button onClick={()=>setShowMoreFF(p=>!p)} style={{marginTop:6,background:"none",border:"none",padding:"4px 0 2px",cursor:"pointer",fontSize:9,fontWeight:700,color:T.gray3,letterSpacing:0.8,display:"block",marginLeft:"auto",fontFamily:"inherit"}}>
                  {showMoreFF?"↑ SHOW LESS":"↓ SHOW MORE"}
                </button>
              </>
            );
          })()}
        </Card>

        {/* AI Diagnosis */}
        <Card>
          <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10 }}>
            <div style={{ display:"flex", alignItems:"center", gap:8 }}>
              <div style={{ width:26, height:26, borderRadius:6, background:T.black, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><path d="M12 2a7 7 0 0 1 7 7c0 3-1.5 5-3.5 6.5V17a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-1.5C6.5 14 5 12 5 9a7 7 0 0 1 7-7z"/><line x1="9" y1="21" x2="15" y2="21"/><line x1="10" y1="17" x2="14" y2="17"/></svg>
              </div>
              <div style={{ fontSize:9, fontWeight:800, color:T.gray3, letterSpacing:1, textTransform:"uppercase" }}>AI Diagnosis</div>
            </div>
            {loading && <span style={{ fontSize:9, color:T.amber, fontWeight:800, letterSpacing:0.8, border:`1px solid ${T.amberBorder}`, padding:"2px 7px", borderRadius:3 }}>ANALYSING</span>}
          </div>
          {loading ? (
            <><Skeleton w="40%" h={10} mb={8}/><Skeleton w="100%" h={13} mb={4}/><Skeleton w="90%" h={13} mb={4}/><Skeleton w="70%" h={13}/></>
          ) : !ai ? (
            <>
              <button onClick={runDiagnosis}
                style={{ display:"flex", alignItems:"center", gap:8, width:"100%",
                  background:T.bgPage, border:`1px solid ${T.border}`,
                  borderRadius:50, padding:"9px 16px", cursor:"pointer", marginBottom:10 }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={T.gray2} strokeWidth="2">
                  <path d="M12 2a7 7 0 0 1 7 7c0 3-1.5 5-3.5 6.5V17a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-1.5C6.5 14 5 12 5 9a7 7 0 0 1 7-7z"/>
                  <line x1="9" y1="21" x2="15" y2="21"/><line x1="10" y1="17" x2="14" y2="17"/>
                </svg>
                <span style={{ fontSize:12, fontWeight:500, color:T.gray2, letterSpacing:0.1 }}>Run AI Diagnosis</span>
              </button>
              <div style={{ paddingTop:8, borderTop:`1px solid ${T.border}`, textAlign:"center" }}>
                <div style={{ fontSize:11, color:T.gray2, fontWeight:700, marginBottom:4 }}>AI can make mistakes. Please double-check all information.</div>
                <div style={{ fontSize:11, color:T.gray3, lineHeight:1.6 }}>Diagnosis is based on historical tickets and service bulletins.</div>
              </div>
            </>
          ) : (
            <>
              {(() => {
                const text = ai.likely_cause || "";
                const matches = [...text.matchAll(/(PRIMARY FAULT|FAULT EVIDENCE|RECOMMENDED ACTION)\s*[:·]?\s*/g)];
                const parts = [];
                if (matches.length > 0) {
                  matches.forEach((match, i) => {
                    if (i===0 && match.index>0) parts.push({ label: null, text: text.slice(0, match.index).trim() });
                    const end = matches[i+1]?.index ?? text.length;
                    parts.push({ label: match[1], text: text.slice(match.index + match[0].length, end).trim() });
                  });
                } else {
                  parts.push({ label: null, text });
                }
                const hasMore = parts.length > 1 || (ai.rec_parts?.length > 0);
                const visibleParts = showMoreAI ? parts : parts.slice(0,1);
                return (<>
                  {visibleParts.map((p, i) => p.label ? (
                    <div key={i} style={{ marginBottom:10, paddingBottom:10, borderBottom: showMoreAI && i < parts.length-1 ? `1px solid ${T.border}` : "none" }}>
                      <div style={{ fontSize:9, fontWeight:700, color:T.gray3, letterSpacing:1, marginBottom:4 }}>{p.label}</div>
                      <div style={{ fontSize:12, color:T.gray1, lineHeight:1.7 }}>{p.text}</div>
                    </div>
                  ) : p.text ? (
                    <div key={i} style={{ fontSize:12, color:T.gray1, lineHeight:1.7, marginBottom:10 }}>{p.text}</div>
                  ) : null)}
                  {hasMore && !showMoreAI && (
                    <button onClick={()=>setShowMoreAI(p=>!p)} style={{marginTop:4,background:"none",border:"none",padding:"4px 0 2px",cursor:"pointer",fontSize:9,fontWeight:700,color:T.gray3,letterSpacing:0.8,display:"block",marginLeft:"auto",fontFamily:"inherit"}}>
                      {"\u2193 SHOW MORE"}
                    </button>
                  )}
                  {showMoreAI && ai.rec_parts?.length>0 && (
                    <div style={{ marginTop:4, paddingTop:10, borderTop:`1px solid ${T.border}` }}>
                      <Label>LIKELY PARTS NEEDED</Label>
                      {ai.rec_parts.map((p,i)=>(
                        <div key={i} style={{ display:"flex", alignItems:"flex-start", gap:6, fontSize:12, color:T.gray1, marginBottom:6 }}>
                          <span style={{ color:T.red, fontWeight:900, flexShrink:0, fontSize:14, lineHeight:1.2 }}>{"\u203a"}</span>
                          <span>{p}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {hasMore && showMoreAI && (
                    <button onClick={()=>setShowMoreAI(p=>!p)} style={{marginTop:6,background:"none",border:"none",padding:"4px 0 2px",cursor:"pointer",fontSize:9,fontWeight:700,color:T.gray3,letterSpacing:0.8,display:"block",marginLeft:"auto",fontFamily:"inherit"}}>
                      {"\u2191 SHOW LESS"}
                    </button>
                  )}
                </>);
              })()}
              <div style={{ marginTop:10, paddingTop:10, borderTop:`1px solid ${T.border}`, textAlign:"center" }}>
                <div style={{ fontSize:11, color:T.gray2, fontWeight:700, marginBottom:4 }}>AI can make mistakes. Please double-check all information.</div>
                <div style={{ fontSize:11, color:T.gray3, lineHeight:1.6 }}>
                  {ai.similar_cases>0 && <span>Based on <strong style={{ color:T.gray1 }}>{ai.similar_cases}</strong> historical tickets. </span>}
                  {ai.ref && <span>Referenced in <button onClick={()=>{const r=resolveTSB(ai.ref);if(r)setTriageDoc({source:r.file,type:"tsb",chunk:r.chunk});}} style={{ background:"none",border:"none",padding:0,cursor:"pointer",fontFamily:"inherit",fontSize:11,fontWeight:700,color:T.red,textDecoration:"underline",textDecorationStyle:"dotted" }}>{ai.ref}</button>.</span>}
                  {(!ai.similar_cases || ai.similar_cases===0) && !ai.ref && <span>Diagnosis is based on historical tickets and service bulletins.</span>}
                </div>
              </div>
            </>
          )}
        </Card>

        {/* Safety */}
        <Card style={{ border:`1.5px solid ${T.redBorder}`, background:T.redBg }}>
          <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:8 }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={T.red} strokeWidth="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <Label color={T.red} extra={{ margin:0 }}>SAFETY</Label>
          </div>
          {(() => {
            const warnings = ai?.safety || autoSafety;
            if (!warnings) return (
              <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                <div style={{ display:"flex", gap:4 }}>
                  {[0,1,2].map(d=><span key={d} style={{ width:5,height:5,borderRadius:"50%",background:T.red,display:"block",animation:"pulse 1s infinite",animationDelay:`${d*0.2}s` }}/>)}
                </div>
                <span style={{ fontSize:12, color:T.red }}>Loading safety warnings…</span>
              </div>
            );
            if (warnings.length === 0) return <div style={{ fontSize:12, color:T.red, fontWeight:700 }}>! Follow standard PPE protocol.</div>;
            return <>
              <div style={{ fontSize:12, fontWeight:800, color:T.red, marginBottom:6 }}>{warnings[0]}</div>
              {warnings.slice(1).map((s,i)=>(
                <div key={i} style={{ fontSize:12, color:T.red, marginBottom:4, display:"flex", gap:5 }}>
                  <span style={{ fontWeight:900, flexShrink:0 }}>!</span><span>{s}</span>
                </div>
              ))}
            </>;
          })()}
        </Card>

        <div style={{ padding:"0 16px" }}>
          <button onClick={onStartRCA} style={{ width:"100%", padding:15, background:T.red, color:T.white, border:"none", borderRadius:6, fontSize:13, fontWeight:800, cursor:"pointer", letterSpacing:0.8 }}>
            START RCA CHECKLIST
          </button>
        </div>
      </div>
    </>
  );
}

function RCATab({ ticket, currentUser, onComplete }) {
  const [phase, setPhase]           = useState("intro");  // intro|skip|checklist|final_assessment
  const [steps, setSteps]           = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [findings, setFindings]     = useState([]);
  const [observation, setObs]       = useState("");
  const [loading, setLoading]       = useState(false);
  const [err, setErr]               = useState("");
  const [notice, setNotice]         = useState("");
  const [warning, setWarning]       = useState("");
  const [finalData, setFinalData]   = useState(null);
  const [showFindings, setShowFindings] = useState(false);
  // Skip state
  const [skipReason, setSkipReason] = useState("");
  const [skipDetail, setSkipDetail] = useState("");
  // Escalation handled in Action tab

  const totalSteps = steps.length;
  const currentStep = steps[currentIdx];
  const done = steps.filter(s=>s.completed).length;
  const pct = totalSteps ? done/totalSteps : 0;

  const startChecklist = async () => {
    setLoading(true); setErr("");
    try {
      const d = await apiRCAGenerate(ticket.ticket_id);
      if (d.error || !d.rca) { setErr(d.error||d.detail||"Failed to load RCA."); return; }
      setSteps(d.rca.steps||[]);
      setPhase("checklist");
    } catch { setErr("Backend offline — cannot load RCA checklist."); }
    finally { setLoading(false); }
  };

  const submitSkip = async () => {
    if (!skipReason) { setErr("Select a skip reason."); return; }
    if (skipReason==="other" && !skipDetail.trim()) { setErr("Please describe the reason."); return; }
    setLoading(true);
    try {
      await apiRCASkip(ticket.ticket_id, skipReason, skipDetail, currentUser?.tech_id||"");
      onComplete(); // unlocks ACTION tab, goes there
    } catch { setErr("Could not record skip — check backend."); }
    finally { setLoading(false); }
  };

  const submitStep = async (outcome) => {
    if (!observation.trim()) { setErr("Describe what you saw before selecting an outcome."); return; }
    setErr(""); setNotice(""); setWarning(""); setLoading(true);
    try {
      const d = await apiRCAStep(ticket.ticket_id, currentIdx+1, outcome, observation.trim());
      const result = d.result || d;
      // Mark step as completed locally
      const updatedSteps = steps.map((s,i)=> i===currentIdx ? {...s, completed:true, outcome, observation:observation.trim()} : s);
      setSteps(updatedSteps);
      setObs("");

      if (result.status==="solved") {
        onComplete(); return;
      }
      if (result.status==="final_assessment") {
        setFinalData(result); setPhase("final_assessment"); return;
      }
      if (result.notice) setNotice(result.notice);
      if (result.warning) setWarning(result.warning);
      if (outcome==="found_issue") setFindings(f=>[...f,{ step:currentIdx+1, title:currentStep?.title||"", observation:observation.trim() }]);
      setCurrentIdx(i => i+1);
    } catch { setErr("Failed to submit step."); }
    finally { setLoading(false); }
  };

  const completeRCA = async () => {
    setLoading(true);
    try {
      await apiRCAComplete(ticket.ticket_id, "proceed");
    } catch { /* non-blocking */ }
    finally { setLoading(false); }
    onComplete();
  };



  const SKIP_REASONS = [
    { v:"familiar_fault",   l:"Familiar fault — resolved this before" },
    { v:"trivial_fix",      l:"Trivial fix — cause immediately obvious" },
    { v:"already_resolved", l:"Already resolved on arrival" },
    { v:"other",            l:"Other" },
  ];



  // ── PHASE: intro ─────────────────────────────────────────────────────────────
  if (phase==="intro") return (
    <div style={{ padding:"24px 16px", display:"flex", flexDirection:"column", gap:12 }}>
      <Card>
        <Label>ROOT CAUSE ANALYSIS</Label>
        <div style={{ fontSize:12, color:T.gray2, lineHeight:1.6, marginBottom:14 }}>
          The RCA checklist guides you through a structured diagnostic process for this fault system. All steps must be completed unless you solve the issue early.
        </div>
        <div style={{ background:"#1A1A1A", border:"1px solid #333", borderRadius:6, padding:"9px 12px", marginBottom:14, display:"flex", alignItems:"flex-start", gap:8 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#999" strokeWidth="2" style={{ flexShrink:0, marginTop:1 }}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <div style={{ fontSize:11, color:"#999", fontWeight:600, lineHeight:1.5 }}>You must complete ALL steps in order, even if you identify an issue partway through. This ensures no secondary faults are missed.</div>
        </div>
        {err && <div style={{ fontSize:12, color:T.red, marginBottom:10 }}>{err}</div>}
        <button onClick={startChecklist} disabled={loading}
          style={{ width:"100%", padding:14, background:loading?"#ccc":T.red, color:T.white, border:"none", borderRadius:6, fontSize:13, fontWeight:800, cursor:loading?"default":"pointer", marginBottom:8 }}>
          {loading ? "LOADING CHECKLIST…" : "START RCA CHECKLIST"}
        </button>
        <button onClick={() => { setPhase("skip"); setErr(""); }}
          style={{ width:"100%", padding:12, background:T.white, color:T.gray2, border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, fontWeight:600, cursor:"pointer" }}>
          Skip RCA — I don't need the checklist
        </button>
      </Card>
    </div>
  );

  // ── PHASE: skip ──────────────────────────────────────────────────────────────
  if (phase==="skip") return (
    <div style={{ padding:"24px 16px" }}>
      <Card>
        <Label>SKIP RCA — SELECT REASON</Label>
        <div style={{ fontSize:12, color:T.gray2, marginBottom:14, lineHeight:1.6 }}>This will be logged in the audit trail. A senior will see your reason when they review the closing approval.</div>
        <div style={{ display:"flex", flexDirection:"column", gap:8, marginBottom:14 }}>
          {SKIP_REASONS.map(r=>(
            <button key={r.v} onClick={()=>setSkipReason(r.v)}
              style={{ padding:"11px 14px", borderRadius:6, fontSize:12, fontWeight:600, cursor:"pointer", textAlign:"left",
                border:`${skipReason===r.v?"2":"1"}px solid ${skipReason===r.v?T.black:T.border}`,
                background:skipReason===r.v?T.black:T.white, color:skipReason===r.v?T.white:T.gray2 }}>
              {r.l}
            </button>
          ))}
        </div>
        {skipReason==="other" && (
          <textarea value={skipDetail} onChange={e=>setSkipDetail(e.target.value)} placeholder="Describe why you are skipping…" rows={3}
            style={{ width:"100%", padding:"10px 12px", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, resize:"none", outline:"none", marginBottom:10 }}/>
        )}
        {err && <div style={{ fontSize:12, color:T.red, marginBottom:10 }}>{err}</div>}
        <button onClick={submitSkip} disabled={loading}
          style={{ width:"100%", padding:14, background:loading?"#ccc":T.black, color:T.white, border:"none", borderRadius:6, fontSize:13, fontWeight:800, cursor:loading?"default":"pointer", marginBottom:8 }}>
          {loading?"LOGGING SKIP…":"CONFIRM SKIP & GO TO ACTION"}
        </button>
        <button onClick={()=>setPhase("intro")} style={{ width:"100%", padding:12, background:"none", color:T.gray2, border:"none", fontSize:12, cursor:"pointer" }}>Go back</button>
      </Card>
    </div>
  );

  // ── PHASE: checklist ─────────────────────────────────────────────────────────
  if (phase==="checklist") return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%" }}>

      {/* Sticky progress header */}
      <div style={{ flexShrink:0, background:T.white, borderBottom:`1px solid ${T.border}`, padding:"12px 14px" }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:7 }}>
          <span style={{ fontSize:9, fontWeight:800, color:T.gray3, letterSpacing:1 }}>ROOT CAUSE ANALYSIS</span>
          <span style={{ fontSize:11, fontWeight:700, color:T.gray2 }}>{done}/{totalSteps}</span>
        </div>
        <div style={{ height:4, background:T.bgPage, borderRadius:3, overflow:"hidden" }}>
          <div style={{ width:`${pct*100}%`, height:"100%", background:T.red, borderRadius:3, transition:"width 0.4s" }}/>
        </div>
        {findings.length>0 && (
          <div style={{ marginTop:8, background:T.amberBg, border:`1px solid ${T.amberBorder}`, borderRadius:6, overflow:"hidden" }}>
            <button onClick={()=>setShowFindings(p=>!p)} style={{ width:"100%", display:"flex", alignItems:"center", justifyContent:"space-between", padding:"7px 10px", background:"none", border:"none", cursor:"pointer", fontFamily:"inherit" }}>
              <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                <span style={{ width:6, height:6, borderRadius:"50%", background:T.amber, display:"inline-block", flexShrink:0 }}/>
                <span style={{ fontSize:10, fontWeight:700, color:T.amber }}>FINDINGS RECORDED: {findings.length}</span>
              </div>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={T.amber} strokeWidth="2.5" style={{ transform:showFindings?"rotate(180deg)":"rotate(0deg)", transition:"transform 0.2s", flexShrink:0 }}><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            {showFindings && (
              <div style={{ padding:"0 10px 8px", borderTop:`1px solid ${T.amberBorder}` }}>
                {findings.map((f,i)=>(
                  <div key={i} style={{ fontSize:11, color:T.gray1, padding:"5px 0", borderBottom:i<findings.length-1?`1px solid ${T.amberBorder}`:"none", wordBreak:"break-word" }}>
                    <span style={{ fontSize:9, fontWeight:700, color:T.amber, marginRight:4 }}>STEP {f.step}</span>{f.observation}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {warning && <div style={{ marginTop:8, background:T.redBg, border:`1px solid ${T.redBorder}`, borderRadius:6, padding:"8px 10px", fontSize:12, color:T.red, fontWeight:600, lineHeight:1.5, wordBreak:"break-word", overflow:"hidden" }}>{warning}</div>}
      </div>

      {/* Scrollable step cards */}
      <div style={{ flex:1, overflowY:"auto", background:T.bgPage, padding:"8px 12px 24px" }}>
        {steps.map((step,i)=>{
          const isDone = step.completed;
          const isCur  = i===currentIdx && !isDone;
          const isPend = i>currentIdx;
          return (
            <div key={i} style={{ background:T.white, border:`1px solid ${isCur?"#ccc":T.border}`, borderRadius:8, overflow:"hidden", opacity:isPend?0.5:1 }}>
              <div style={{ display:"flex", alignItems:"center", gap:10, padding:"12px 14px" }}>
                <div style={{ width:26, height:26, borderRadius:"50%", flexShrink:0, background:isDone?T.green:isCur?T.black:T.bgPage, display:"flex", alignItems:"center", justifyContent:"center", border:`1px solid ${isDone?T.green:isCur?T.black:T.border}` }}>
                  {isDone ? <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={T.white} strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                           : <span style={{ fontSize:11, fontWeight:700, color:isCur?T.white:T.gray3 }}>{i+1}</span>}
                </div>
                <span style={{ fontSize:13, fontWeight:isCur?700:600, color:isDone?T.gray3:T.black, flex:1 }}>{step.title}</span>
                {isDone && (
                  <span style={{ fontSize:10, fontWeight:700, padding:"2px 8px", borderRadius:3,
                    background:step.outcome==="found_issue"?T.amberBg:step.outcome==="solved"?T.greenBg:T.bgPage,
                    color:step.outcome==="found_issue"?T.amber:step.outcome==="solved"?T.green:T.gray3 }}>
                    {step.outcome==="found_issue"?"FOUND ISSUE":step.outcome==="solved"?"SOLVED":"CLEAR"}
                  </span>
                )}
              </div>

              {isCur && (
                <div style={{ padding:"0 14px 14px", borderTop:`1px solid ${T.bgPage}` }}>
                  {/* Step content */}
                  <div style={{ marginTop:10, marginBottom:10 }}>
                    <div style={{ fontSize:12, color:T.gray1, lineHeight:1.65 }}>{step.content}</div>
                  </div>
                  {step.what_to_look_for && (
                    <div style={{ marginBottom:8 }}>
                      <Label>WHAT TO LOOK FOR</Label>
                      <div style={{ fontSize:12, color:T.gray1, lineHeight:1.6 }}>{step.what_to_look_for}</div>
                    </div>
                  )}
                  {step.learning_point && (
                    <div style={{ background:T.yellowBg, border:`1px solid ${T.yellowBorder}`, borderRadius:6, padding:"9px 12px", marginBottom:12 }}>
                      <Label color={T.yellowBorder} extra={{ marginBottom:3 }}>LEARNING POINT</Label>
                      <div style={{ fontSize:12, color:"#5d4037", fontWeight:600, lineHeight:1.5 }}>{step.learning_point}</div>
                    </div>
                  )}

                  {/* Observation input */}
                  <Label>WHAT DID YOU SEE AT THIS STEP? *</Label>
                  <textarea value={observation} onChange={e=>setObs(e.target.value)} placeholder="Briefly describe what you observed…" rows={2}
                    style={{ width:"100%", padding:"10px 12px", border:`1px solid ${err&&!observation.trim()?T.red:T.border}`, borderRadius:6, fontSize:12, resize:"none", outline:"none", marginBottom:10, background:T.bgPage }}/>

                  {err && <div style={{ fontSize:12, color:T.red, marginBottom:10 }}>{err}</div>}

                  {/* Outcome buttons */}
                  <Label>WHAT IS YOUR OUTCOME?</Label>
                  <div style={{ display:"flex", flexDirection:"column", gap:7 }}>
                    {[
                      { v:"found_issue", l:"Found Issue — spotted something relevant", c:T.amber },
                      { v:"inconclusive", l:"Inconclusive — nothing found at this step", c:T.gray2 },
                      { v:"solved", l:"Solved — issue fully fixed, engine running", c:T.green },
                    ].map(opt=>(
                      <button key={opt.v} onClick={()=>submitStep(opt.v)} disabled={loading}
                        style={{ width:"100%", display:"flex", alignItems:"center", gap:10, padding:"11px 12px", borderRadius:6,
                          border:`1px solid ${opt.c}`, background:`${opt.c}12`, cursor:loading?"default":"pointer", textAlign:"left", fontFamily:"inherit" }}>
                        <div style={{ width:10, height:10, borderRadius:"50%", background:opt.c, flexShrink:0 }}/>
                        <span style={{ fontSize:12, color:opt.c, fontWeight:700 }}>{opt.l}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
        </div>
      </div>
  );

  // ── PHASE: final_assessment ───────────────────────────────────────────────────
  if (phase==="final_assessment") {
    const allFindings = findings.filter((f,i,arr)=>arr.findIndex(x=>x.step===f.step)===i);
    const hasFindings = allFindings.length > 0;
    return (
      <div style={{ padding:"24px 16px" }}>
        <Card>
          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:12 }}>
            <div style={{ width:32, height:32, borderRadius:"50%", background:hasFindings?T.amberBg:T.greenBg, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
              {hasFindings
                ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={T.amber} strokeWidth="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={T.green} strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              }
            </div>
            <div>
              <div style={{ fontSize:13, fontWeight:800, color:T.black }}>Checklist Complete</div>
              <div style={{ fontSize:11, color:T.gray3 }}>{hasFindings ? `${allFindings.length} finding${allFindings.length!==1?"s":""} recorded` : "No issues found during inspection"}</div>
            </div>
          </div>

          {hasFindings && (
            <div style={{ background:T.amberBg, border:`1px solid ${T.amberBorder}`, borderRadius:6, padding:"10px 12px", marginBottom:14 }}>
              <div style={{ fontSize:9, fontWeight:800, color:T.amber, letterSpacing:1, marginBottom:8 }}>FINDINGS SUMMARY</div>
              {allFindings.map((f,i)=>(
                <div key={i} style={{ marginBottom: i < allFindings.length-1 ? 8 : 0, paddingBottom: i < allFindings.length-1 ? 8 : 0, borderBottom: i < allFindings.length-1 ? `1px solid ${T.amberBorder}` : "none" }}>
                  <div style={{ fontSize:9, fontWeight:700, color:T.amber, marginBottom:2 }}>STEP {f.step} · {f.title}</div>
                  <div style={{ fontSize:12, color:T.gray1, lineHeight:1.5, wordBreak:"break-word" }}>{f.observation}</div>
                </div>
              ))}
            </div>
          )}

          <div style={{ background:T.bgPage, borderRadius:6, padding:"10px 12px", marginBottom:14, fontSize:11, color:T.gray2, lineHeight:1.6 }}>
            Review your findings and proceed to the Action tab to mark this ticket resolved or file an escalation.
          </div>
          {err && <div style={{ fontSize:12, color:T.red, marginBottom:10 }}>{err}</div>}
          <button onClick={completeRCA} disabled={loading}
            style={{ width:"100%", padding:14, background:loading?"#ccc":T.red, color:T.white, border:"none", borderRadius:6, fontSize:13, fontWeight:800, cursor:loading?"default":"pointer", letterSpacing:0.5 }}>
            {loading?"LOADING…":"CONTINUE TO ACTION →"}
          </button>
        </Card>
      </div>
    );
  }

}

// ─── ACTION TAB ───────────────────────────────────────────────────────────────
function ActionTab({ ticket, currentUser, rcaDone }) {
  const [path, setPath]           = useState("");   // "resolve" | "escalate"
  const [form, setForm]           = useState({ fixType:"", action:"", parts:"", disposition:"", testResults:"", hours:"", ai:"", notes:"", safetyConfirmed:false });
  const [photos, setPhotos]       = useState([]);
  const [approver, setApprover]   = useState(null);
  const [loading, setLoading]     = useState(false);
  const [err, setErr]             = useState("");
  const [done, setDone]           = useState(false);
  const [doneMsg, setDoneMsg]     = useState("");
  // Escalation form (when path=escalate)
  const [escType, setEscType]     = useState("parts_warranty");
  const [escReason, setEscReason] = useState("");
  const [escName, setEscName]     = useState("");
  const [escId, setEscId]         = useState("");
  const photoRef = useRef(null);

  // Gate: RCA must be done
  if (!rcaDone) return (
    <div style={{ padding:"48px 24px 24px", display:"flex", flexDirection:"column", alignItems:"center", gap:12 }}>
      <div style={{ width:52, height:52, borderRadius:"50%", background:T.bgPage, border:`1px solid ${T.border}`, display:"flex", alignItems:"center", justifyContent:"center" }}>
        <span style={{ fontSize:22 }}>🔒</span>
      </div>
      <div style={{ fontSize:15, fontWeight:800, color:T.black }}>Complete RCA First</div>
      <div style={{ fontSize:12, color:T.gray3, textAlign:"center", lineHeight:1.6 }}>Go to the RCA tab to complete or skip the diagnostic checklist before closing this ticket.</div>
    </div>
  );

  if (done) return (
    <div style={{ padding:"52px 24px 24px", display:"flex", flexDirection:"column", alignItems:"center", gap:16 }}>
      <div style={{ width:64, height:64, borderRadius:"50%", background:T.greenBg, display:"flex", alignItems:"center", justifyContent:"center" }}>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={T.green} strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
      </div>
      <div style={{ fontSize:18, fontWeight:900, color:T.black }}>Submitted</div>
      <div style={{ fontSize:13, color:T.gray2, textAlign:"center", lineHeight:1.6 }}>{doneMsg}</div>
      <div style={{ background:T.greenBg, border:`1px solid ${T.green}`, borderRadius:8, padding:"12px 16px", width:"100%" }}>
        <div style={{ fontSize:10, color:T.green, fontWeight:700, marginBottom:3, letterSpacing:0.8 }}>TICKET ID</div>
        <div style={{ fontSize:13, color:T.black, fontWeight:700 }}>{ticket.ticket_id}</div>
      </div>
    </div>
  );

  // Path selection
  if (!path) return (
    <div style={{ padding:"24px 16px" }}>
      <Card>
        <Label>WHAT IS THE OUTCOME?</Label>
        <div style={{ fontSize:12, color:T.gray2, marginBottom:16, lineHeight:1.6 }}>Select what happened so we can route your submission for senior approval.</div>
        <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
          <button onClick={()=>setPath("resolve")}
            style={{ padding:"16px 14px", borderRadius:8, border:`1px solid ${T.black}`, background:T.black, cursor:"pointer", textAlign:"left", fontFamily:"inherit" }}>
            <div style={{ fontSize:13, fontWeight:800, color:T.white, marginBottom:3 }}>✓ I fixed it</div>
            <div style={{ fontSize:12, color:T.gray4 }}>Submit work for senior closing approval</div>
          </button>
          <button onClick={()=>setPath("escalate")}
            style={{ padding:"16px 14px", borderRadius:8, border:`1px solid ${T.border}`, background:T.white, cursor:"pointer", textAlign:"left", fontFamily:"inherit" }}>
            <div style={{ fontSize:13, fontWeight:800, color:T.black, marginBottom:3 }}>↑ I need something to proceed</div>
            <div style={{ fontSize:12, color:T.gray2 }}>Parts, budget approval, or senior tech on site</div>
          </button>
        </div>
      </Card>
    </div>
  );

  // ── PATH: escalate ────────────────────────────────────────────────────────────
  if (path==="escalate") {
    const [escApprover, setEscApprover] = useState(null);
    const submitEsc = async () => {
      if (!escReason.trim()||!escApprover) { setErr("All fields required."); return; }
      setLoading(true); setErr("");
      try {
        const d = await apiEscalate(ticket.ticket_id, { escalation_type:escType, reason:escReason.trim(), approver_id:escApprover.manager_id, approver_name:escApprover.name });
        if (d.error||d.detail) throw new Error(d.error||d.detail);
        setDoneMsg("Escalation sent. Your supervisor will be in touch."); setDone(true);
      } catch(e) { setErr(e.message||"Failed to escalate."); }
      finally { setLoading(false); }
    };
    return (
      <div style={{ padding:"16px 14px 32px", background:T.bgPage }}>
        <Card>
          <div style={{ fontSize:14, fontWeight:800, color:T.black, marginBottom:16 }}>Escalation Request</div>
          <Label>ESCALATION TYPE *</Label>
          <div style={{ display:"flex", flexWrap:"wrap", gap:6, marginBottom:14 }}>
            {[{v:"parts_warranty",l:"Parts / Warranty & Billing"},{v:"technical_support",l:"Technical Support"}].map(o=>(
              <Chip key={o.v} label={o.l} active={escType===o.v} onPress={()=>setEscType(o.v)}/>
            ))}
          </div>
          <Label>REASON *</Label>
          <textarea value={escReason} onChange={e=>setEscReason(e.target.value)} placeholder="Describe what you need and why…" rows={3}
            style={{ width:"100%", padding:"10px 12px", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, resize:"none", outline:"none", marginBottom:14 }}/>
          <Label>SELECT APPROVER *</Label>
          <div style={{ marginBottom:14 }}>
            <ApproverPicker value={escApprover} onChange={setEscApprover}/>
          </div>
          {err && <div style={{ fontSize:12, color:T.red, marginBottom:10 }}>{err}</div>}
          <button onClick={submitEsc} disabled={loading}
            style={{ width:"100%", padding:14, background:loading?"#ccc":T.red, color:T.white, border:"none", borderRadius:6, fontSize:13, fontWeight:800, cursor:loading?"default":"pointer", marginBottom:8 }}>
            {loading?"SENDING…":"SEND ESCALATION REQUEST"}
          </button>
          <button onClick={()=>{setPath("");setErr("");}} style={{ width:"100%", padding:12, background:"none", color:T.gray2, border:"none", fontSize:12, cursor:"pointer" }}>Go back</button>
        </Card>
      </div>
    );
  }

  // ── PATH: resolve ─────────────────────────────────────────────────────────────
  const set = (k,v) => setForm(f=>({...f,[k]:v}));

  const handlePhoto = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    const fd = new FormData(); fd.append("file",file); fd.append("context","resolution");
    try {
      const r = await fetch(`${API}/api/upload/${ticket.ticket_id}`,{method:"POST",body:fd});
      if (!r.ok) throw new Error();
      const d = await r.json();
      setPhotos(p=>[...p,{ id:d.file_id, name:file.name, url:URL.createObjectURL(file) }]);
    } catch { setErr("Photo upload failed."); }
    e.target.value="";
  };

  const submitResolution = async () => {
    if (!form.fixType||!form.action||!form.testResults.trim()||!form.hours||!form.ai||!form.safetyConfirmed||!approver) {
      setErr("Please complete all required fields including safety confirmation and approver details."); return;
    }
    setLoading(true); setErr("");
    try {
      const body = {
        tech_id:              currentUser?.tech_id||"",
        fix_type:             form.fixType,
        action_taken:         form.action,
        parts_actually_used:  form.parts ? form.parts.split(",").map(s=>s.trim()).filter(Boolean) : [],
        parts_disposition:    form.disposition,
        test_results:         form.testResults.trim(),
        labor_hours:          parseFloat(form.hours),
        ai_diagnosis_correct: form.ai,
        tech_notes:           form.notes,
        photo_references:     photos.map(p=>p.id),
        safety_confirmed:     true,
        approver_id:          approver.manager_id,
        approver_name:        approver.name,
      };
      const d = await apiRequestApproval(ticket.ticket_id, body);
      if (d.error||d.detail) throw new Error(d.error||d.detail);
      setDoneMsg(`Closing approval request sent to ${approver?.name}. Awaiting senior sign-off.`); setDone(true);
    } catch(e) { setErr(e.message||"Submission failed. Check backend."); }
    finally { setLoading(false); }
  };

  const chips = (key, opts) => (
    <div style={{ display:"flex", flexWrap:"wrap", gap:6 }}>
      {opts.map(o=>(
        <Chip key={o.v} label={o.l} active={form[key]===o.v} onPress={()=>set(key,o.v)}/>
      ))}
    </div>
  );

  return (
    <div style={{ padding:"16px 14px 32px", background:T.bgPage }}>
      <input ref={photoRef} type="file" accept="image/*" capture="environment" onChange={handlePhoto} style={{ display:"none" }}/>
      <Card>
        <div style={{ fontSize:14, fontWeight:800, color:T.black, marginBottom:16 }}>Resolution Form</div>

        {/* Fix type */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:700, color:T.gray2, letterSpacing:0.5, marginBottom:6 }}>SHORT TERM OR LONG TERM FIX? *</div>
          {chips("fixType",[{v:"short_term",l:"Short Term"},{v:"long_term",l:"Long Term"}])}
          {form.fixType==="short_term" && (
            <div style={{ marginTop:8, background:T.amberBg, border:`1px solid ${T.amberBorder}`, borderRadius:6, padding:"8px 10px", fontSize:11, color:T.amberDark, fontWeight:600, lineHeight:1.5 }}>
              Short term fix — your supervisor will be notified to schedule a follow-up.
            </div>
          )}
        </div>

        {/* Action taken */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:700, color:T.gray2, letterSpacing:0.5, marginBottom:6 }}>ACTION TAKEN *</div>
          {chips("action",[{v:"replaced_part",l:"Replaced Part"},{v:"cleaned",l:"Cleaned"},{v:"adjusted",l:"Adjusted"},{v:"other",l:"Other"}])}
        </div>

        {/* Parts used */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:700, color:T.gray2, letterSpacing:0.5, marginBottom:6 }}>PARTS USED</div>
          <input value={form.parts} onChange={e=>set("parts",e.target.value)} placeholder="e.g. DEF-SENSOR-001, FILTER-042"
            style={{ width:"100%", padding:"10px 12px", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, outline:"none", background:T.bgPage }}/>
        </div>

        {/* Parts disposition */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:700, color:T.gray2, letterSpacing:0.5, marginBottom:6 }}>PARTS DISPOSITION</div>
          {chips("disposition",[{v:"retained_for_oem",l:"Retained for OEM"},{v:"returned",l:"Returned"},{v:"disposed",l:"Disposed"}])}
        </div>

        {/* Test results */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:700, color:T.gray2, letterSpacing:0.5, marginBottom:6 }}>TEST RESULTS AFTER FIX *</div>
          <textarea value={form.testResults} onChange={e=>set("testResults",e.target.value)} placeholder="Describe what happened after the fix was applied — e.g. fault codes cleared, engine started normally…" rows={3}
            style={{ width:"100%", padding:"10px 12px", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, resize:"none", outline:"none", background:T.bgPage }}/>
        </div>

        {/* Labor hours */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:700, color:T.gray2, letterSpacing:0.5, marginBottom:6 }}>LABOR HOURS *</div>
          <input type="number" value={form.hours} onChange={e=>set("hours",e.target.value)} placeholder="e.g. 1.5"
            style={{ width:"100%", padding:"10px 12px", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, outline:"none", background:T.bgPage }}/>
        </div>

        {/* Photos */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:700, color:T.gray2, letterSpacing:0.5, marginBottom:6 }}>PHOTOS OF COMPLETED WORK</div>
          <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
            {photos.map((p,i)=>(
              <div key={i} style={{ position:"relative" }}>
                <img src={p.url} alt={p.name} style={{ width:64, height:64, borderRadius:6, objectFit:"cover" }}/>
                <button onClick={()=>setPhotos(ps=>ps.filter((_,j)=>j!==i))} style={{ position:"absolute", top:-6, right:-6, width:18, height:18, borderRadius:"50%", background:T.red, border:"none", color:T.white, cursor:"pointer", fontSize:12, display:"flex", alignItems:"center", justifyContent:"center" }}>×</button>
              </div>
            ))}
            <button onClick={()=>photoRef.current?.click()} style={{ width:64, height:64, borderRadius:6, border:`2px dashed ${T.border}`, background:T.bgPage, cursor:"pointer", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:4 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={T.gray3} strokeWidth="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
              <span style={{ fontSize:9, color:T.gray3, fontWeight:600 }}>ADD</span>
            </button>
          </div>
        </div>

        {/* AI correct */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:700, color:T.gray2, letterSpacing:0.5, marginBottom:6 }}>WAS AI DIAGNOSIS CORRECT? *</div>
          {chips("ai",[{v:"yes",l:"Yes"},{v:"partially",l:"Partially"},{v:"no",l:"No"}])}
        </div>

        {/* Tech notes */}
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontWeight:700, color:T.gray2, letterSpacing:0.5, marginBottom:6 }}>TECH NOTES</div>
          <textarea value={form.notes} onChange={e=>set("notes",e.target.value)} placeholder="Additional observations…" rows={2}
            style={{ width:"100%", padding:"10px 12px", border:`1px solid ${T.border}`, borderRadius:6, fontSize:12, resize:"none", outline:"none", background:T.bgPage }}/>
        </div>

        {/* Safety confirmation */}
        <div style={{ marginBottom:14 }}>
          <button onClick={()=>set("safetyConfirmed",!form.safetyConfirmed)}
            style={{ display:"flex", alignItems:"center", gap:10, width:"100%", padding:"12px 14px", borderRadius:6,
              border:`2px solid ${form.safetyConfirmed?T.green:T.border}`, background:form.safetyConfirmed?T.greenBg:T.white, cursor:"pointer", textAlign:"left", fontFamily:"inherit" }}>
            <div style={{ width:20, height:20, borderRadius:4, border:`2px solid ${form.safetyConfirmed?T.green:T.border}`, background:form.safetyConfirmed?T.green:"transparent", display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
              {form.safetyConfirmed && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={T.white} strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>}
            </div>
            <span style={{ fontSize:12, color:form.safetyConfirmed?T.green:T.gray2, fontWeight:form.safetyConfirmed?700:500, lineHeight:1.4 }}>
              I confirm this equipment is safe to return to operation *
            </span>
          </button>
        </div>

        {/* Approver */}
        <div style={{ borderTop:`1px solid ${T.border}`, paddingTop:14, marginBottom:14 }}>
          <Label>CLOSING APPROVER *</Label>
          <div style={{ fontSize:11, color:T.gray3, marginBottom:10, lineHeight:1.5 }}>A named senior must approve before this ticket closes. They will receive your full submission for review.</div>
          <ApproverPicker value={approver} onChange={setApprover}/>
        </div>

        {err && <div style={{ fontSize:12, color:T.red, marginBottom:10, fontWeight:600 }}>{err}</div>}
        <button onClick={submitResolution} disabled={loading}
          style={{ width:"100%", padding:15, background:loading?"#ccc":T.red, color:T.white, border:"none", borderRadius:6, fontSize:13, fontWeight:800, cursor:loading?"default":"pointer", letterSpacing:0.5 }}>
          {loading?"SUBMITTING…":"SEND FOR CLOSING APPROVAL"}
        </button>
      </Card>

      <div style={{ background:T.white, border:`1px solid ${T.border}`, borderRadius:6, padding:"10px 12px" }}>
        <div style={{ fontSize:9, fontWeight:700, color:T.gray3, letterSpacing:1, marginBottom:3 }}>AUDIT TRAIL</div>
        <div style={{ fontSize:11, color:T.gray2, lineHeight:1.6 }}>Resolution logged with timestamp, tech ID, and full decision trail. Senior approval required before ticket closes.</div>
      </div>
    </div>
  );
}

// ─── REPORTS SCREEN ───────────────────────────────────────────────────────────
function ReportsScreen({ currentUser }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr]         = useState("");
  const [section, setSection] = useState("pending");
  const [expandedReport, setExpanded] = useState(null);

  useEffect(()=>{
    if (!currentUser) return;
    setLoading(true); setErr("");
    apiGetReports(currentUser.tech_id)
      .then(d=>{
        if (!d?.success) throw new Error(d?.detail || "Unknown error");
        setData(d);
      })
      .catch(e=>{ setErr(e.message||"Could not load reports — check backend."); })
      .finally(()=>setLoading(false));
  },[currentUser]);

  const STATUS_BADGE = {
    pending:  { label:"PENDING",        bg:T.amberBg, color:T.amber },
    approved: { label:"APPROVED",       bg:T.greenBg, color:T.green },
    rejected: { label:"ACTION NEEDED",  bg:T.redBg,   color:T.red   },
  };
  const ESC_BADGE = { parts_warranty:"Parts / Warranty & Billing", technical_support:"Technical Support", unsafe:"UNSAFE" };

  // Derive counts from actual arrays (not a counts field from backend)
  const pendingCount    = data?.pending_approvals?.length    || 0;
  const completedCount  = data?.completed_reports?.length    || 0;
  const escalationCount = data?.escalation_history?.length   || 0;

  const tabs = [
    { id:"pending",     label:"Pending",     count: pendingCount },
    { id:"completed",   label:"Reports",     count: completedCount },
    { id:"escalations", label:"Escalations", count: escalationCount },
  ];

  function EmptyState({ icon, title, subtitle }) {
    return (
      <div style={{ padding:"52px 24px", display:"flex", flexDirection:"column", alignItems:"center", gap:12 }}>
        <div style={{ fontSize:36 }}>{icon}</div>
        <div style={{ fontSize:14, fontWeight:800, color:T.black }}>{title}</div>
        <div style={{ fontSize:12, color:T.gray3, textAlign:"center", lineHeight:1.6 }}>{subtitle}</div>
      </div>
    );
  }

  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%" }}>
      <TopBar />
      {/* Filter tabs */}
      <div style={{ background:T.white, padding:"10px 14px", borderBottom:`1px solid ${T.border}`, display:"flex", gap:6, flexShrink:0 }}>
        {tabs.map(s=>(
          <button key={s.id} onClick={()=>setSection(s.id)}
            style={{ padding:"5px 12px", borderRadius:20, fontSize:11, fontWeight:700, cursor:"pointer", border:"none",
              background:section===s.id?T.black:T.white, color:section===s.id?T.white:T.gray2,
              boxShadow:section===s.id?"none":`0 0 0 1px ${T.border}`,
              display:"flex", alignItems:"center", gap:5 }}>
            {s.label}
            {s.count>0 && (
              <span style={{ minWidth:16, height:16, borderRadius:8, padding:"0 4px",
                background:section===s.id?"rgba(255,255,255,0.25)":T.red,
                color:T.white, fontSize:9, fontWeight:800,
                display:"inline-flex", alignItems:"center", justifyContent:"center" }}>
                {s.count}
              </span>
            )}
          </button>
        ))}
      </div>

      <div style={{ flex:1, overflowY:"auto", background:T.bgPage, padding:"8px 14px" }}>
        {loading
          ? <div style={{ padding:40, textAlign:"center", color:T.gray3, fontSize:13 }}>Loading…</div>
          : err
          ? <div style={{ background:T.redBg, border:`1px solid ${T.redBorder}`, borderRadius:8, padding:"14px 16px", margin:"8px 0", fontSize:12, color:T.red, lineHeight:1.6 }}>
              <strong>Backend error:</strong> {err}<br/>
              <span style={{ opacity:0.8 }}>Make sure FastAPI is running on port 8000.</span>
            </div>
          : !data
          ? <EmptyState icon="📡" title="No data" subtitle="Could not load — check backend."/>
          : (
          <>
            {section==="pending" && (
              pendingCount===0
              ? <EmptyState icon="✅" title="Nothing pending" subtitle={"Submit a resolution from the ACTION tab\nand it will appear here for senior review."}/>
              : data.pending_approvals.map((item,i)=>{
                const badge = STATUS_BADGE[item.status] || STATUS_BADGE.pending;
                return (
                  <div key={i} style={{ background:T.white, borderRadius:8, padding:"12px 14px", marginBottom:8, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" }}>
                    <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:8 }}>
                      <div>
                        <div style={{ fontSize:13, fontWeight:800, color:T.black }}>{item.customer}</div>
                        <div style={{ fontSize:10, color:T.gray3, marginTop:1 }}>{item.ticket_id}</div>
                      </div>
                      <div style={{ background:badge.bg, border:`1px solid ${badge.color}`, borderRadius:4, padding:"3px 8px" }}>
                        <span style={{ fontSize:9, fontWeight:800, color:badge.color, letterSpacing:0.8 }}>{badge.label}</span>
                      </div>
                    </div>
                    <div style={{ fontSize:11, color:T.gray2, marginBottom:6 }}>
                      {item.fix_type==="short_term"?"Short term":"Long term"} · {(item.action_taken||"").replace(/_/g," ")} · {item.labor_hours}h
                    </div>
                    <div style={{ fontSize:10, color:T.gray3 }}>Approver: {item.approver_name} · {item.submitted_at ? new Date(item.submitted_at).toLocaleDateString() : "—"}</div>
                    {item.status==="rejected" && item.approver_notes && (
                      <div style={{ marginTop:10, background:T.redBg, border:`1px solid ${T.redBorder}`, borderRadius:6, padding:"9px 12px" }}>
                        <div style={{ fontSize:10, fontWeight:700, color:T.red, marginBottom:4 }}>SENIOR FEEDBACK</div>
                        <div style={{ fontSize:12, color:T.red, lineHeight:1.5 }}>{item.approver_notes}</div>
                      </div>
                    )}
                  </div>
                );
              })
            )}

            {section==="completed" && (
              completedCount===0
              ? <EmptyState icon="📋" title="No completed reports yet" subtitle={"Tickets approved by a senior will\nappear here with their full report."}/>
              : data.completed_reports.map((item,i)=>(
                <div key={i} onClick={()=>setExpanded(expandedReport===i?null:i)}
                  style={{ background:T.white, borderRadius:8, padding:"12px 14px", marginBottom:8, boxShadow:"0 1px 3px rgba(0,0,0,0.04)", cursor:"pointer" }}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
                    <div style={{ flex:1 }}>
                      <div style={{ fontSize:13, fontWeight:800, color:T.black }}>{item.customer}</div>
                      <div style={{ fontSize:10, color:T.gray3, marginTop:1 }}>{item.ticket_id} · {item.resolved_at ? new Date(item.resolved_at).toLocaleDateString() : "—"}</div>
                      <div style={{ marginTop:6, display:"inline-flex", alignItems:"center", gap:4, padding:"2px 8px", borderRadius:4,
                        background:item.fix_type==="short_term"?T.amberBg:T.greenBg,
                        border:`1px solid ${item.fix_type==="short_term"?T.amberBorder:T.green}` }}>
                        <span style={{ fontSize:9, fontWeight:800, color:item.fix_type==="short_term"?T.amber:T.green, letterSpacing:0.5 }}>
                          {item.fix_type==="short_term"?"SHORT TERM FIX":"LONG TERM FIX"}
                        </span>
                      </div>
                    </div>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={T.gray3} strokeWidth="2"
                      style={{ transform:expandedReport===i?"rotate(180deg)":"rotate(0deg)", transition:"transform 0.2s", marginTop:4 }}>
                      <polyline points="6 9 12 15 18 9"/>
                    </svg>
                  </div>
                  {expandedReport===i && item.report && (
                    <div style={{ marginTop:12, paddingTop:12, borderTop:`1px solid ${T.border}` }}>
                      <div style={{ fontSize:12, color:T.gray1, lineHeight:1.6, whiteSpace:"pre-wrap", fontFamily:"monospace", background:T.bgPage, padding:"10px 12px", borderRadius:6 }}>
                        {typeof item.report==="string" ? item.report : JSON.stringify(item.report, null, 2)}
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}

            {section==="escalations" && (
              escalationCount===0
              ? <EmptyState icon="↑" title="No escalations" subtitle={"Escalations submitted from RCA\nor the ACTION tab appear here."}/>
              : data.escalation_history.map((item,i)=>(
                <div key={i} style={{ background:T.white, borderRadius:8, padding:"12px 14px", marginBottom:8, boxShadow:"0 1px 3px rgba(0,0,0,0.04)" }}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:8 }}>
                    <div>
                      <div style={{ fontSize:13, fontWeight:800, color:T.black }}>{item.customer}</div>
                      <div style={{ fontSize:10, color:T.gray3, marginTop:1 }}>{item.ticket_id}</div>
                    </div>
                    <div style={{ background:item.escalation_type==="unsafe"?T.redBg:T.bgPage,
                      border:`1px solid ${item.escalation_type==="unsafe"?T.red:T.border}`,
                      borderRadius:4, padding:"3px 8px" }}>
                      <span style={{ fontSize:9, fontWeight:800, color:item.escalation_type==="unsafe"?T.red:T.gray2, letterSpacing:0.8 }}>
                        {ESC_BADGE[item.escalation_type]||item.escalation_type}
                      </span>
                    </div>
                  </div>
                  {item.reason && <div style={{ fontSize:11, color:T.gray2, marginBottom:6, lineHeight:1.5 }}>{item.reason}</div>}
                  <div style={{ fontSize:10, color:T.gray3 }}>Approver: {item.approver_name||"—"} · {item.escalated_at ? new Date(item.escalated_at).toLocaleDateString() : "—"}</div>
                </div>
              ))
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ─── SETTINGS SCREEN ──────────────────────────────────────────────────────────
function SettingsScreen({ backendStatus, currentUser, onLogout }) {
  const rows = [
    ["Technician ID",  currentUser?.tech_id || "—"],
    ["Name",           currentUser?.name    || "—"],
    ["Cert Level",     currentUser ? `Level ${currentUser.cert}` : "—"],
    ["Depot",          currentUser?.depot   || "—"],
    ["Backend",        backendStatus==="online" ? "🟢 Online" : "🔴 Offline"],
    ["Backend URL",    API],
    ["Offline Mode",   "Auto-sync on reconnect"],
    ["Language",       "English / Español"],
    ["Model",          "Mistral (Ollama local)"],
    ["Version",        "0.2.0"],
  ];
  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%" }}>
      <TopBar />
      <div style={{ flex:1, overflowY:"auto", background:T.bgPage, padding:16 }}>
        {rows.map(([l,v])=>(
          <div key={l} style={{ background:T.white, padding:"14px 16px", marginBottom:1, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
            <span style={{ fontSize:13, color:T.gray1 }}>{l}</span>
            <span style={{ fontSize:12, color:T.gray3, fontWeight:500 }}>{v}</span>
          </div>
        ))}
        <button onClick={onLogout} style={{ marginTop:20, width:"100%", background:"#FEF5F5", border:"1px solid #F5C6C6", borderRadius:10, padding:"14px", fontSize:14, fontWeight:800, color:T.red, cursor:"pointer" }}>
          Sign Out
        </button>
      </div>
    </div>
  );
}

// ─── ROOT ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen]           = useState("home");
  const [ticket, setTicket]           = useState(null);
  const [allTickets, setAllTickets]   = useState([]);
  const [ticketsLoading, setTLoad]    = useState(true);
  const [currentUser, setCurrentUser] = useState(null);
  const [backendStatus, setBStatus]   = useState("checking");
  const [toast, setToast]             = useState("");
  const [triageCache, setTriageCache] = useState({});
  const [chatCache, setChatCache]     = useState({});

  useEffect(()=>{
    let faultCodeMap = {};
    apiHealth()
      .then(()=>{ setBStatus("online"); return Promise.all([apiListTickets(), apiListFaultCodes()]); })
      .then(([d, fc])=>{
        // Build fault code → system map from real backend data
        if (fc?.fault_codes) {
          faultCodeMap = Object.fromEntries(
            Object.entries(fc.fault_codes).map(([code, info]) => [code, info.system])
          );
          Object.assign(FAULT_SYSTEM_MAP, faultCodeMap);
        }
        if (!d?.tickets?.length) return;
        const mapped = d.tickets.map(t=>({
          ticket_id:         t.ticket_id,
          serial_number:     t.serial_number,
          customer:          t.customer,
          location:          t.location,
          equipment_model:   t.equipment_model||"X15",
          fault_codes:       t.fault_codes||[],
          systems:           [...new Set((t.fault_codes||[]).map(c=>faultCodeMap[c]).filter(Boolean))],
          priority:          (t.shutdown_active||t.derate_active)?"High":"Medium",
          sla_label:         t.shutdown_active?"1:00H":t.derate_active?"2:00H":"4:00H",
          tech_id:           t.tech_id,
          equipment_hours:   t.equipment_hours||0,
          warranty:          t.warranty_expiry ? (new Date(t.warranty_expiry)>new Date()?"Active":"Expired") : (t.warranty_active?"Active":"Expired"),
          issue_description: t.issue_description,
          equipment_type:    t.equipment_type||"",
          cm_version:        t.cm_version||"",
          inactive_codes:    t.inactive_codes||[],
          submitted_at:      t.submitted_at||"",
          warranty_expiry:   t.warranty_expiry||"",
          billable_to:       t.billable_to||"",
          coverage_type:     t.coverage_type||"",
          freeze_frame:{
            def_level:          t.freeze_frame?.def_level_pct!=null?`${t.freeze_frame.def_level_pct}%`:"—",
            def_level_pct:      t.freeze_frame?.def_level_pct??null,
            engine_rpm:         t.freeze_frame?.engine_rpm!=null?`${t.freeze_frame.engine_rpm.toLocaleString()}`:"—",
            coolant_temp:       t.freeze_frame?.coolant_temp_f!=null?`${t.freeze_frame.coolant_temp_f}°F`:"—",
            coolant_temp_f:     t.freeze_frame?.coolant_temp_f??null,
            oil_pressure:       t.freeze_frame?.oil_pressure_psi!=null?`${t.freeze_frame.oil_pressure_psi} psi`:"—",
            oil_pressure_psi:   t.freeze_frame?.oil_pressure_psi??null,
            fuel_pressure_kpa:  t.freeze_frame?.fuel_pressure_kpa??null,
            dpf_soot_load_pct:  t.freeze_frame?.dpf_soot_load_pct??null,
            boost_pressure_psi: t.freeze_frame?.boost_pressure_psi??null,
            exhaust_temp_f:     t.freeze_frame?.exhaust_temp_f??null,
            load_pct:           t.freeze_frame?.load_pct??null,
          },
          triage:{likely_cause:"Open ticket → run triage for AI diagnosis.",confidence:0,similar_cases:0,ref:""},
          safety:["Run triage to load safety warnings for this fault."],
          rca_steps:[],
          derate_active:   t.derate_active||false,
          shutdown_active: t.shutdown_active||false,
          status:          t.status || (t.resolved_at ? "resolved" : "open"),
        }));
        setAllTickets(mapped); setTLoad(false);
      })
      .catch(()=>{ setBStatus("offline"); setAllTickets(TICKETS); setTLoad(false); });
  },[]);

  const tickets = currentUser ? allTickets.filter(t=>t.tech_id===currentUser.tech_id) : [];

  const showToast = (msg) => { setToast(msg); setTimeout(()=>setToast(""),2500); };
  const handleLogin  = (user) => { setCurrentUser(user); showToast(`Welcome, ${user.name.split(" ")[0]}! ${allTickets.filter(t=>t.tech_id===user.tech_id).length} ticket(s) assigned.`); };
  const handleLogout = () => { setCurrentUser(null); setScreen("home"); setTicket(null); };
  const nav = id => {
    // Troubleshoot tap: always go to tickets list (even from ticket_detail)
    if (id === "tickets") { setScreen("tickets"); setTicket(null); return; }
    // Already on that tab — do nothing
    if (id === screen) return;
    setScreen(id); setTicket(null);
  };
  const openTicket = t => { setTicket(t); setScreen("ticket_detail"); };

  const navActive = screen==="home"?"home"
    :(screen==="tickets"||screen==="ticket_detail")?"tickets"
    :screen==="reports"?"reports":"settings";

  const OfflineBanner = () => backendStatus==="offline" ? (
    <div style={{ background:"#FFF8EC", borderBottom:`1px solid #CF8300`, padding:"5px 14px", fontSize:11, color:"#917200", fontWeight:600, flexShrink:0 }}>
      ⚡ Demo mode — backend offline. Start FastAPI to enable live AI.
    </div>
  ) : null;

  return (
    <>
      <style>{`
        *{box-sizing:border-box;margin:0;padding:0}
        body{background:#111;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
        ::-webkit-scrollbar{width:0}
        input::placeholder,textarea::placeholder{color:#aaa}
        @keyframes pulse{0%,80%,100%{opacity:.3;transform:scale(.8)}40%{opacity:1;transform:scale(1)}}
        @keyframes fadein{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        @keyframes slidein{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:translateY(0)}}
        @keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
      `}</style>

      <div style={{ width:390, height:844, background:currentUser?T.white:T.black, borderRadius:44, overflow:"hidden", display:"flex", flexDirection:"column", boxShadow:"0 40px 100px rgba(0,0,0,0.7)", position:"relative" }}>
        {/* Status bar */}
        <div style={{ background:T.black, padding:"10px 24px 6px", display:"flex", justifyContent:"space-between", alignItems:"center", flexShrink:0 }}>
          <span style={{ fontSize:12, fontWeight:700, color:T.white }}>9:41</span>
          <div style={{ width:110, height:26, background:"#111", borderRadius:18, border:"2px solid #2a2a2a" }}/>
          <div style={{ display:"flex", gap:4 }}>
            <svg width="15" height="11" viewBox="0 0 15 11" fill={T.white}><rect x="0" y="4" width="3" height="7" rx="1"/><rect x="4" y="2.5" width="3" height="8.5" rx="1"/><rect x="8" y="1" width="3" height="10" rx="1"/><rect x="12" y="0" width="3" height="11" rx="1"/></svg>
          </div>
        </div>

        {!currentUser ? <LoginScreen onLogin={handleLogin}/> : (
          <>
            <div style={{ flex:1, overflow:"hidden", display:"flex", flexDirection:"column" }}>
              <OfflineBanner/>
              {screen==="home"          && <HomeScreen tickets={tickets} ticketsLoading={ticketsLoading} currentUser={currentUser} onSelectTicket={openTicket}/>}
              {screen==="tickets"       && <TicketsScreen tickets={tickets} currentUser={currentUser} onSelect={openTicket}/>}
              {screen==="ticket_detail" && ticket && <TicketDetail ticket={ticket} currentUser={currentUser} backendOnline={backendStatus==="online"} triageCache={triageCache} setTriageCache={setTriageCache} chatCache={chatCache} setChatCache={setChatCache}/>}
              {screen==="reports"       && <ReportsScreen currentUser={currentUser}/>}
              {screen==="settings"      && <SettingsScreen backendStatus={backendStatus} currentUser={currentUser} onLogout={handleLogout}/>}
            </div>
            <BottomNav active={navActive} onNav={nav}/>
          </>
        )}

        {toast && (
          <div onClick={()=>setToast("")} style={{ position:"absolute", bottom:currentUser?76:24, left:16, right:16, background:T.black, color:T.white, borderRadius:8, padding:"10px 14px", fontSize:12, fontWeight:600, textAlign:"center", animation:"fadein 0.3s ease", zIndex:999 }}>
            {toast}
          </div>
        )}
      </div>
    </>
  );
}