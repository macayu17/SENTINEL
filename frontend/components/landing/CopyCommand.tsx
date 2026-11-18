'use client';

import { useState } from 'react';

export default function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard blocked; the command stays selectable
    }
  };
  return (
    <div className="flex max-w-full flex-wrap items-center gap-3 rounded-[28px] bg-[#24242a] py-2 pl-7 pr-2 text-fg">
      <code className="code-pill select-all break-all text-[clamp(14px,3.5vw,18px)]">{command}</code>
      <button type="button" onClick={copy} className="btn btn-pill btn-accent min-h-[46px] px-[22px] font-bold" aria-live="polite">{copied ? 'copied' : 'copy'}</button>
    </div>
  );
}
