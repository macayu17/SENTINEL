/** Orange scrolling tape. Items repeat once so the loop is seamless; reduced motion holds it still. */
export default function Ticker({ items, size = 'sm' }: { items: Array<{ label: string; value: string }>; size?: 'sm' | 'lg' }) {
  const loop = [...items, ...items];
  const large = size === 'lg';
  return (
    <div aria-label="Ticker" className="overflow-hidden whitespace-nowrap bg-accent text-ink">
      <div
        className={`ticker-track inline-flex ${large ? 'py-3.5 font-display text-xl font-bold tracking-[-0.01em]' : 'py-1.5 text-[13px] font-semibold'}`}
        style={{ ['--ticker-duration' as string]: `${Math.max(30, items.length * 5)}s` }}
      >
        {loop.map((item, index) => (
          <span key={index} className="inline-flex" aria-hidden={index >= items.length || undefined}>
            <span className={`inline-flex gap-2 ${large ? 'px-[22px]' : 'px-4'}`}>
              <span>{item.label}</span>
              <span className="font-medium">{item.value}</span>
            </span>
            <span aria-hidden="true">·</span>
          </span>
        ))}
      </div>
    </div>
  );
}
