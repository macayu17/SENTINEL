import Link from 'next/link';
import type { ReactNode } from 'react';

// Optional nav link that only a developer machine sets, as "Label|/path" in .env.local.
const [localLabel, localHref] = (process.env.NEXT_PUBLIC_LOCAL_LINK ?? '').split('|');

/** Renders the developer-machine link, or nothing in the public build. */
export function LocalNavLink({ className = 'btn' }: { className?: string }) {
  return localHref ? <Link href={localHref} className={className}>{localLabel}</Link> : null;
}

/** Top bar for the internal screens: wordmark, context on the left, actions on the right. */
export default function AppHeader({ context, actions, wide = false, children }: {
  context?: ReactNode;
  actions?: ReactNode;
  /** Dashboard runs full width; other screens sit in a centred column. */
  wide?: boolean;
  children?: ReactNode;
}) {
  return (
    <header className="border-b border-line">
      <div className={`flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 ${wide ? '' : 'mx-auto max-w-[1320px]'}`}>
        <div className="flex min-w-0 flex-wrap items-center gap-x-5 gap-y-1">
          <Link href="/" className="inline-flex min-h-10 items-center font-display text-xl font-bold tracking-[-0.02em] text-fg no-underline">
            SENTINEL
          </Link>
          {context}
        </div>
        <div className="flex flex-wrap items-center gap-2"><LocalNavLink />{actions}</div>
      </div>
      {children}
    </header>
  );
}
