/**
 * SignalProgress — live, per-signal scan progress. Lists every Key and Supporting
 * signal and checks each off as the backend step that covers it resolves. While a
 * signal's step is still running, a highlight rotates through the in-flight signals
 * so the user watches them being worked one by one. No green anywhere.
 */
import { useEffect, useState } from "react";
import type { StepKey, StepStatus } from "../lib/scan";
import { FUNCTION_SIGNALS } from "../lib/scan";
import { CATALOG, KEY_SIGNALS, SUPPORTING_SIGNALS, type CatalogId } from "../lib/scan-contract";
import type { StepState } from "./ProgressCard";

type SigStatus = "scanning" | "done" | "failed";

function stepStatusFor(id: CatalogId, steps: StepState[]): SigStatus {
  const covering = (Object.keys(FUNCTION_SIGNALS) as StepKey[]).filter((k) => FUNCTION_SIGNALS[k].includes(id));
  const states = covering.map((k) => steps.find((s) => s.key === k)?.status ?? "pending") as StepStatus[];
  if (states.some((s) => s === "pending")) return "scanning";
  if (states.length > 0 && states.every((s) => s === "failed")) return "failed";
  return "done";
}

export function SignalProgress({ steps }: { steps: StepState[] }) {
  const all = [...KEY_SIGNALS, ...SUPPORTING_SIGNALS];
  const statusById = new Map<CatalogId, SigStatus>(all.map((id) => [id, stepStatusFor(id, steps)]));
  const scanning = all.filter((id) => statusById.get(id) === "scanning");
  const done = all.filter((id) => statusById.get(id) !== "scanning").length;

  // Rotate a highlight through the currently-scanning signals.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (scanning.length === 0) return;
    const t = setInterval(() => setTick((n) => n + 1), 450);
    return () => clearInterval(t);
  }, [scanning.length]);
  const activeId = scanning.length ? scanning[tick % scanning.length] : null;

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span className="card-title">Scanning {all.length} signals</span>
        <span className="tnum secondary">{done}/{all.length}</span>
      </div>
      <div style={{ height: 6, borderRadius: 999, background: "var(--ia-offwhite)", overflow: "hidden", marginBottom: 18 }}>
        <div style={{ height: "100%", width: `${(done / all.length) * 100}%`, background: "var(--ia-blue)", borderRadius: 999, transition: "width 240ms cubic-bezier(.22,.61,.36,1)" }} />
      </div>

      <Group title="Key signals" ids={KEY_SIGNALS} statusById={statusById} activeId={activeId} />
      <div style={{ height: 14 }} />
      <Group title="Supporting signals" ids={SUPPORTING_SIGNALS} statusById={statusById} activeId={activeId} />
    </div>
  );
}

function Group({ title, ids, statusById, activeId }: { title: string; ids: CatalogId[]; statusById: Map<CatalogId, SigStatus>; activeId: CatalogId | null }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 8 }}>{title}</div>
      <div style={{ display: "grid", gap: 2 }}>
        {ids.map((id) => (
          <Row key={id} id={id} status={statusById.get(id) ?? "scanning"} active={id === activeId} />
        ))}
      </div>
    </div>
  );
}

function Row({ id, status, active }: { id: CatalogId; status: SigStatus; active: boolean }) {
  const entry = CATALOG[id];
  const scanning = status === "scanning";
  const failed = status === "failed";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 30, padding: "0 8px", borderRadius: 8, background: active ? "var(--ia-blue-soft)" : "transparent", transition: "background 200ms ease" }}>
      <span aria-hidden style={{
        width: 16, height: 16, borderRadius: 999, flexShrink: 0, fontSize: 11,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        color: failed ? "var(--ia-orange)" : "var(--ia-white)",
        background: scanning ? "var(--ia-gray-2)" : failed ? "transparent" : "var(--ia-blue)",
        border: failed ? "1.5px solid var(--ia-orange)" : "none",
        animation: scanning && active ? "pulse 1s ease-in-out infinite" : "none",
      }}>
        {scanning ? "" : failed ? "!" : "✓"}
      </span>
      <span style={{ flexShrink: 0, width: 16, textAlign: "center", color: "var(--ia-gray-3)" }}>{entry.glyph}</span>
      <span style={{ flex: 1, fontSize: 14, color: scanning && !active ? "var(--ia-gray-3)" : "var(--ia-black)" }}>{entry.label}</span>
      <span className="secondary" style={{ fontSize: 12 }}>
        {scanning ? (active ? "scanning…" : "queued") : failed ? "unavailable" : "scanned"}
      </span>
    </div>
  );
}
