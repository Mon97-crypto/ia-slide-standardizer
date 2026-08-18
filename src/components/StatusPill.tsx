/**
 * StatusPill — Vercel-style status: a small dot and a word, never a banner.
 * Ready (blue) → Scanning (amber) → Ready.
 */
export type Status = "ready" | "scanning";

export function StatusPill({ status }: { status: Status }) {
  const scanning = status === "scanning";
  return (
    <span
      className="label"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px",
        borderRadius: 999,
        background: "var(--ia-white)",
        border: "1px solid var(--ia-gray-1)",
        color: "var(--ia-black)",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 7,
          height: 7,
          borderRadius: 999,
          background: scanning ? "var(--ia-orange)" : "var(--ia-blue)",
          animation: scanning ? "pulse 1.2s ease-in-out infinite" : "none",
        }}
      />
      {scanning ? "Scanning" : "Ready"}
    </span>
  );
}
