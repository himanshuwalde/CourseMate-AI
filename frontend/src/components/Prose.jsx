import React from "react";

const INLINE = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*|\[\d+\])/g;

function inline(text, sources) {
  return text
    .replace(/`/g, "")
    .split(INLINE)
    .filter(Boolean)
    .map((part, i) => {
      if (/^\*\*.+\*\*$/.test(part) || /^__.+__$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
      if (/^\*.+\*$/.test(part)) return <em key={i}>{part.slice(1, -1)}</em>;
      const m = part.match(/^\[(\d+)\]$/);
      if (m) {
        const src = sources?.find((s) => s.index === Number(m[1]));
        const title = src ? `${src.filename}${src.page ? `, p.${src.page}` : ""}` : "";
        return (
          <sup key={i} className="cite" title={title}>
            {m[1]}
          </sup>
        );
      }
      return <React.Fragment key={i}>{part}</React.Fragment>;
    });
}

/** Renders the small subset of markdown that the model produces: headings, bullets, numbers, bold, italics. */
export default function Prose({ text, sources }) {
  const out = [];
  let list = null;
  const flush = () => {
    if (list) {
      const Tag = list.type;
      out.push(<Tag key={`l${out.length}`}>{list.items}</Tag>);
      list = null;
    }
  };
  text.split("\n").forEach((raw, n) => {
    const line = raw.trim();
    let m;
    if (!line) return flush();
    if ((m = line.match(/^#{1,6}\s+(.*)$/))) {
      flush();
      out.push(<h4 key={n}>{inline(m[1], sources)}</h4>);
    } else if ((m = line.match(/^[-*\u2022]\s+(.*)$/))) {
      if (!list || list.type !== "ul") {
        flush();
        list = { type: "ul", items: [] };
      }
      list.items.push(<li key={n}>{inline(m[1], sources)}</li>);
    } else if ((m = line.match(/^\d{1,2}[.)]\s+(.*)$/))) {
      if (!list || list.type !== "ol") {
        flush();
        list = { type: "ol", items: [] };
      }
      list.items.push(<li key={n}>{inline(m[1], sources)}</li>);
    } else {
      flush();
      out.push(<p key={n}>{inline(line, sources)}</p>);
    }
  });
  flush();
  return <div className="prose">{out}</div>;
}
