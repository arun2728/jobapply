import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import clsx from "clsx";

interface Props {
  children: string;
  className?: string;
  /** Tight styling for previews inside cards / line-clamp containers.
   *  Drops block margins and renders headings as inline-bold so
   *  ``line-clamp-2`` produces a clean 2-line excerpt regardless of
   *  whether the source starts with a heading, list, or paragraph. */
  compact?: boolean;
}

// Tailwind-styled component overrides so the rendered markdown picks
// up the rest of the dark theme (white text, neutral links, etc.)
// without us needing the @tailwindcss/typography plugin.
const components: Components = {
  h1: ({ node: _node, ...props }) => (
    <h1
      className="mt-4 text-lg font-semibold text-white first:mt-0"
      {...props}
    />
  ),
  h2: ({ node: _node, ...props }) => (
    <h2
      className="mt-4 text-base font-semibold text-white first:mt-0"
      {...props}
    />
  ),
  h3: ({ node: _node, ...props }) => (
    <h3
      className="mt-3 text-sm font-semibold uppercase tracking-wide text-neutral-300 first:mt-0"
      {...props}
    />
  ),
  h4: ({ node: _node, ...props }) => (
    <h4 className="mt-3 text-sm font-semibold text-neutral-200" {...props} />
  ),
  p: ({ node: _node, ...props }) => (
    <p className="mb-3 leading-relaxed last:mb-0" {...props} />
  ),
  ul: ({ node: _node, ...props }) => (
    <ul
      className="mb-3 list-disc space-y-1 pl-6 marker:text-neutral-600 last:mb-0"
      {...props}
    />
  ),
  ol: ({ node: _node, ...props }) => (
    <ol
      className="mb-3 list-decimal space-y-1 pl-6 marker:text-neutral-600 last:mb-0"
      {...props}
    />
  ),
  li: ({ node: _node, ...props }) => (
    <li className="leading-relaxed" {...props} />
  ),
  a: ({ node: _node, ...props }) => (
    <a
      className="text-white underline underline-offset-2 hover:text-neutral-300"
      target="_blank"
      rel="noreferrer"
      {...props}
    />
  ),
  strong: ({ node: _node, ...props }) => (
    <strong className="font-semibold text-white" {...props} />
  ),
  em: ({ node: _node, ...props }) => (
    <em className="italic text-neutral-200" {...props} />
  ),
  blockquote: ({ node: _node, ...props }) => (
    <blockquote
      className="my-3 border-l-2 border-neutral-700 pl-3 text-neutral-400"
      {...props}
    />
  ),
  hr: () => <hr className="my-4 border-neutral-800" />,
  table: ({ node: _node, ...props }) => (
    <div className="my-3 overflow-x-auto">
      <table
        className="min-w-full border-collapse text-left text-sm"
        {...props}
      />
    </div>
  ),
  th: ({ node: _node, ...props }) => (
    <th
      className="border-b border-neutral-700 px-3 py-2 font-semibold text-neutral-200"
      {...props}
    />
  ),
  td: ({ node: _node, ...props }) => (
    <td
      className="border-b border-neutral-800 px-3 py-2 text-neutral-400"
      {...props}
    />
  ),
  code: ({ node: _node, className, children, ...props }) => {
    // Inline code vs fenced block: react-markdown doesn't pass an
    // explicit `inline` flag in v9, but fenced blocks come with a
    // `language-*` class while inline code never does.
    const isBlock = (className || "").startsWith("language-");
    if (isBlock) {
      return (
        <pre className="my-3 overflow-x-auto rounded bg-black/70 p-3 font-mono text-xs text-neutral-200">
          <code className={className} {...props}>
            {children}
          </code>
        </pre>
      );
    }
    return (
      <code
        className="rounded bg-neutral-800 px-1 py-0.5 font-mono text-[0.85em] text-neutral-200"
        {...props}
      >
        {children}
      </code>
    );
  },
};

// Compact variant used for card previews. Everything renders inline
// or with zero margin so a parent with ``line-clamp-2`` produces a
// clean 2-line excerpt. We deliberately do NOT set a text color on
// any of these — the wrapper's color (e.g. ``text-neutral-600``)
// propagates so the preview stays visually subdued and doesn't
// compete with the card's title / status badge / metadata.
const compactComponents: Components = {
  h1: ({ node: _node, ...props }) => (
    <span className="font-semibold" {...props} />
  ),
  h2: ({ node: _node, ...props }) => (
    <span className="font-semibold" {...props} />
  ),
  h3: ({ node: _node, ...props }) => (
    <span className="font-semibold" {...props} />
  ),
  h4: ({ node: _node, ...props }) => (
    <span className="font-semibold" {...props} />
  ),
  p: ({ node: _node, ...props }) => <span {...props} />,
  ul: ({ node: _node, ...props }) => <span className="ml-1" {...props} />,
  ol: ({ node: _node, ...props }) => <span className="ml-1" {...props} />,
  li: ({ node: _node, children, ...props }) => (
    <span {...props}>· {children} </span>
  ),
  a: ({ node: _node, ...props }) => <span {...props} />,
  strong: ({ node: _node, ...props }) => (
    <span className="font-semibold" {...props} />
  ),
  em: ({ node: _node, ...props }) => <span className="italic" {...props} />,
  blockquote: ({ node: _node, ...props }) => <span {...props} />,
  hr: () => <span> · </span>,
  br: () => <span> </span>,
  code: ({ node: _node, children, ...props }) => (
    <span className="font-mono text-[0.85em]" {...props}>
      {children}
    </span>
  ),
};

/** Renders untrusted markdown safely (react-markdown does not pass
 *  raw HTML through by default — no need for a sanitizer plugin).
 *
 *  In ``compact`` mode no default text color is applied so callers
 *  can dial down contrast (e.g. a muted ``text-neutral-600`` excerpt
 *  on a dense card). In normal mode we default to ``text-neutral-300``
 *  so the body text reads cleanly on the dark page backdrop. */
export default function Markdown({ children, className, compact }: Props) {
  return (
    <div
      className={clsx(
        "text-sm",
        !compact && "text-neutral-300",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={compact ? compactComponents : components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
