import { formatStatus } from "@/lib/format";

export type PdfResultRow = {
  id: string;
  resume_id: string;
  candidate_label: string | null;
  overall_score: string | number;
  mandatory_status: string;
  review_required: boolean;
  score_breakdown?: Array<{
    display_name: string;
    weight: string;
    score: string;
    contribution: string;
    status: string;
    mandatory: boolean;
    passage: string | null;
  }>;
};

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function scoreLabel(score: number): string {
  if (score >= 80) return "Strong match";
  if (score >= 60) return "Good match";
  if (score >= 40) return "Partial match";
  return "Weak match";
}

function buildHtml(opts: {
  jobTitle: string;
  provider?: string;
  rows: PdfResultRow[];
  detailed: boolean;
}): string {
  const { jobTitle, provider, rows, detailed } = opts;
  const generated = new Date().toLocaleString();
  const bodyRows = rows
    .map((row, index) => {
      const score = Math.round(Number(row.overall_score));
      const name = escapeHtml(row.candidate_label?.trim() || `Candidate ${row.resume_id.slice(0, 8)}`);
      const scoreText = Number.isNaN(score) ? "—" : `${score}%`;
      const detail =
        detailed && row.score_breakdown?.length
          ? `<tr class="detail"><td colspan="6">${row.score_breakdown
              .map((item) => {
                const passage = item.passage
                  ? `<div class="passage">“${escapeHtml(item.passage)}”</div>`
                  : "";
                return `<div class="criterion"><strong>${escapeHtml(item.display_name)}</strong>${
                  item.mandatory ? " · Must have" : ""
                } · score ${escapeHtml(String(item.score))} · weight ${escapeHtml(
                  String(item.weight),
                )} · +${escapeHtml(String(item.contribution))} pts · ${escapeHtml(
                  formatStatus(item.status),
                )}${passage}</div>`;
              })
              .join("")}</td></tr>`
          : "";
      return `<tr>
        <td>${index + 1}</td>
        <td>${name}</td>
        <td>${scoreText}<div class="muted">${scoreLabel(Number.isNaN(score) ? 0 : score)}</div></td>
        <td>${escapeHtml(formatStatus(row.mandatory_status))}</td>
        <td>${row.review_required ? "Yes" : "No"}</td>
        <td class="mono">${escapeHtml(row.resume_id.slice(0, 8))}…</td>
      </tr>${detail}`;
    })
    .join("");

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(jobTitle)} · candidate results</title>
  <style>
    @page { margin: 16mm; }
    body { font-family: ui-sans-serif, system-ui, sans-serif; color: #0f172a; font-size: 12px; }
    h1 { font-size: 20px; margin: 0 0 4px; }
    .meta { color: #64748b; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #e2e8f0; padding: 8px 6px; text-align: left; vertical-align: top; }
    th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: #64748b; }
    .muted { color: #64748b; font-size: 11px; margin-top: 2px; }
    .mono { font-family: ui-monospace, monospace; font-size: 11px; color: #64748b; }
    .detail td { background: #f8fafc; border-bottom: 1px solid #cbd5e1; }
    .criterion { margin: 0 0 8px; line-height: 1.4; }
    .passage { margin-top: 4px; color: #475569; font-style: italic; }
  </style>
</head>
<body>
  <h1>${escapeHtml(jobTitle)}</h1>
  <p class="meta">${rows.length} candidate${rows.length === 1 ? "" : "s"} · ${
    detailed ? "Detailed report" : "Summary"
  }${provider ? ` · provider ${escapeHtml(provider)}` : ""} · generated ${escapeHtml(generated)}</p>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Candidate</th>
        <th>Score</th>
        <th>Mandatory</th>
        <th>Review</th>
        <th>Resume</th>
      </tr>
    </thead>
    <tbody>${bodyRows || `<tr><td colspan="6">No candidates</td></tr>`}</tbody>
  </table>
</body>
</html>`;
}

/** Print via a hidden iframe so browsers do not block a pop-up. */
export function openResultsPdf(opts: {
  jobTitle: string;
  provider?: string;
  rows: PdfResultRow[];
  detailed: boolean;
}): void {
  const html = buildHtml(opts);
  const iframe = document.createElement("iframe");
  iframe.setAttribute("title", "PDF export");
  iframe.style.position = "fixed";
  iframe.style.right = "0";
  iframe.style.bottom = "0";
  iframe.style.width = "0";
  iframe.style.height = "0";
  iframe.style.border = "0";
  iframe.style.opacity = "0";
  iframe.style.pointerEvents = "none";
  document.body.appendChild(iframe);

  const frameWindow = iframe.contentWindow;
  const frameDoc = frameWindow?.document;
  if (!frameWindow || !frameDoc) {
    document.body.removeChild(iframe);
    throw new Error("Unable to prepare PDF export in this browser.");
  }

  frameDoc.open();
  frameDoc.write(html);
  frameDoc.close();

  const cleanup = () => {
    window.setTimeout(() => {
      if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
    }, 1000);
  };

  const triggerPrint = () => {
    try {
      frameWindow.focus();
      frameWindow.print();
    } finally {
      cleanup();
    }
  };

  // Give the iframe a moment to layout before opening the print dialog.
  window.setTimeout(triggerPrint, 300);
}
