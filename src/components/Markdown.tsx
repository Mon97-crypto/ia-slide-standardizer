/**
 * Markdown — a small, safe renderer for the subset the Ask briefings use: headings
 * (#..####), bold (**), links [text](url), bullet and numbered lists, paragraphs.
 * Builds React elements (no dangerouslySetInnerHTML), so untrusted text can't inject.
 */
import React from "react";

const INLINE = /(\*\*([^*]+)\*\*)|(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/;

function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let rest = text;
  let key = 0;
  for (;;) {
    const m = INLINE.exec(rest);
    if (!m) {
      if (rest) nodes.push(rest);
      break;
    }
    if (m.index > 0) nodes.push(rest.slice(0, m.index));
    if (m[1]) nodes.push(<strong key={key++}>{m[2]}</strong>);
    else if (m[3]) nodes.push(<a key={key++} href={m[5]} target="_blank" rel="noreferrer">{m[4]}</a>);
    rest = rest.slice(m.index + m[0].length);
  }
  return nodes;
}

export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const Tag = level <= 2 ? "h3" : "h4";
      blocks.push(React.createElement(Tag, { key: key++, className: "md-h" }, renderInline(h[2])));
      i++;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: React.ReactNode[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(<li key={items.length}>{renderInline(lines[i].replace(/^\s*[-*]\s+/, ""))}</li>);
        i++;
      }
      blocks.push(<ul key={key++} className="md-ul">{items}</ul>);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: React.ReactNode[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(<li key={items.length}>{renderInline(lines[i].replace(/^\s*\d+\.\s+/, ""))}</li>);
        i++;
      }
      blocks.push(<ol key={key++} className="md-ul">{items}</ol>);
      continue;
    }

    const para = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])) {
      para.push(lines[i]);
      i++;
    }
    blocks.push(<p key={key++} className="md-p">{renderInline(para.join(" "))}</p>);
  }

  return <div className="markdown-answer">{blocks}</div>;
}
