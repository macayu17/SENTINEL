import Link from 'next/link';
import type { ReactNode } from 'react';

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
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </header>
  );
}
