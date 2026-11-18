import Link from 'next/link';
import BreakIt from '@/components/landing/BreakIt';
import CopyCommand from '@/components/landing/CopyCommand';
import LiveCard from '@/components/landing/LiveCard';
import ScenarioPicker from '@/components/landing/ScenarioPicker';
import Ticker from '@/components/ui/Ticker';

const GITHUB = 'https://github.com/macayu17/sentinel';

const STEPS = [
  ['1. bots trade.', '40 bots buy and sell in a simulated market. some are fast, some are huge, some are just random.'],
  ['2. sentinel watches.', 'every tick, it checks how many orders are waiting and how fast they are disappearing.'],
  ['3. you get warned.', 'if the market is about to run dry, or someone is parking a huge order, you see it first.'],
];

const BOTS = [
  ['market maker', 'quotes both sides, all day'],
  ['HFT', 'reacts in a microsecond'],
  ['institutional', 'huge orders, sliced up'],
  ['retail', 'small trades, gut feeling'],
  ['informed', 'trades toward fair value'],
  ['noise', 'pure random flow'],
  ['liquidity trader', 'has to trade, now'],
  ['momentum', 'follows the trend'],
  ['mean reversion', 'fades big moves'],
  ['sentiment', 'follows the mood'],
  ['spoofer', 'fake orders, spoofing mode only'],
];

const TAPE = [
  { label: 'SIM', value: 'order book live' },
  { label: 'BOTS', value: '11 kinds' },
  { label: 'FASTEST', value: '1 μs' },
  { label: 'SCENARIOS', value: '7' },
  { label: 'SIGNAL', value: 'liquidity stress' },
  { label: 'SIGNAL', value: 'large orders' },
  { label: 'REPORT', value: 'json + pdf' },
];

const display = 'm-0 font-display font-extrabold tracking-[-0.05em]';
const band = 'mx-auto flex max-w-[1280px] flex-col px-5 py-[clamp(72px,10vw,120px)] sm:px-10';

export default function Home() {
  return (
    <div className="text-lg">
      <section className="bg-ink text-fg">
        <header className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-4 px-5 py-6 sm:px-10">
          <span className="font-display text-[26px] font-extrabold tracking-[-0.03em]">sentinel</span>
          <nav aria-label="Primary" className="flex flex-wrap items-center gap-x-7 gap-y-2 font-medium">
            <a href="#how" className="no-underline">how it works</a>
            <Link href="/docs" className="no-underline">docs</Link>
            <a href={GITHUB} className="no-underline">github</a>
            <Link href="/start" className="btn btn-pill btn-light min-h-[46px] px-[22px] font-bold">try it</Link>
          </nav>
        </header>
        <div className="mx-auto grid max-w-[1280px] items-center gap-14 px-5 pb-[110px] pt-[clamp(32px,6vw,72px)] sm:px-10" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 480px), 1fr))' }}>
          <div className="flex flex-col gap-7">
            <h1 className={`${display} text-[clamp(56px,9vw,104px)] leading-[0.9]`}>the market is about to break.</h1>
            <p className="m-0 font-display text-[clamp(30px,4vw,44px)] font-bold leading-none tracking-[-0.03em] text-accent">and you&apos;ll know first.</p>
            <p className="m-0 max-w-[500px] text-xl text-[#b9b7b0]">sentinel runs a fake stock market full of trading bots, and warns you when it&apos;s about to run out of buyers.</p>
            <div className="flex flex-wrap gap-3">
              <Link href="/start" className="btn btn-pill btn-accent min-h-[60px] px-[30px] text-xl font-bold">try the simulator</Link>
              <a href={GITHUB} className="btn btn-pill min-h-[60px] bg-white/10 px-[26px] text-xl font-bold">see the code</a>
            </div>
          </div>
          <LiveCard />
        </div>
      </section>

      <Ticker items={TAPE} size="lg" />

      <section className="on-paper bg-paper text-ink">
        <div className={`${band} gap-14`}>
          <h2 className={`${display} max-w-[900px] text-[clamp(52px,8vw,96px)] leading-[0.92]`}>40 bots. one market. zero chill.</h2>
          <div className="grid gap-8" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            {[['11', 'bot personalities'], ['7', 'ways to ruin their day'], ['1μs', 'for the fastest bot to react']].map(([value, label]) => (
              <div key={label} className="flex flex-col">
                <span className={`${display} text-[clamp(80px,12vw,120px)] leading-[0.9]`}>{value}</span>
                <span className="text-xl font-medium">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="how" className="bg-ink text-fg">
        <div className={`${band} gap-6`}>
          <p className="m-0 mb-4 text-xl font-bold text-accent">how it works</p>
          {STEPS.map(([title, body]) => (
            <div key={title} className="grid items-baseline gap-x-10 gap-y-2 border-t border-fg/15 py-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))' }}>
              <h3 className="m-0 font-display text-[clamp(44px,6vw,72px)] font-extrabold leading-[0.95] tracking-[-0.04em]">{title}</h3>
              <p className="m-0 max-w-[480px] text-xl">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="break" className="on-paper bg-paper text-ink">
        <div className={`${band} gap-9`}>
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="flex flex-col gap-2.5">
              <span className="font-bold text-accent-deep">try it</span>
              <h2 className={`${display} text-[clamp(52px,8vw,96px)] leading-[0.92]`}>try to break it.</h2>
            </div>
            <p className="m-0 max-w-[420px] text-xl text-paper-muted">this is a tiny order book. mess with it and watch the risk score react.</p>
          </div>
          <BreakIt />
        </div>
      </section>

      <section className="bg-ink text-fg">
        <div className={`${band} gap-10`}>
          <h2 className={`${display} text-[clamp(52px,8vw,96px)] leading-[0.92]`}>meet the bots.</h2>
          <ul className="m-0 flex list-none flex-wrap gap-3 p-0">
            {BOTS.map(([name, about]) => (
              <li key={name} className="inline-flex flex-wrap items-baseline gap-2.5 rounded-full bg-[#26262c] px-6 py-3.5">
                <span className="font-display text-[26px] font-extrabold tracking-[-0.02em]">{name}</span>
                <span className="text-base">{about}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="on-paper bg-paper text-ink">
        <div className={`${band} gap-9`}>
          <h2 className={`${display} text-[clamp(52px,8vw,96px)] leading-[0.92]`}>pick your chaos.</h2>
          <ScenarioPicker />
        </div>
      </section>

      <section className="bg-ink text-fg">
        <div className={`${band} !grid items-end gap-14`} style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 440px), 1fr))' }}>
          <div className="flex flex-col gap-2">
            <span className={`${display} text-[clamp(110px,16vw,180px)] leading-[0.85] !tracking-[-0.06em]`}>0.90</span>
            <span className="max-w-[440px] text-xl text-[#b9b7b0]">how well the warning model sees a liquidity crunch coming a minute out, on NASDAQ stocks it never trained on (ROC-AUC, where 1.0 is perfect).</span>
          </div>
          <div className="flex flex-col gap-3">
            <p className="m-0 font-display text-[clamp(28px,3.5vw,40px)] font-bold leading-[1.05] tracking-[-0.03em]">trained on five full days of real NASDAQ order books.</p>
            <p className="m-0 font-display text-[clamp(28px,3.5vw,40px)] font-bold leading-[1.05] tracking-[-0.03em] text-[#b9b7b0]">presented at IEEE ICWITE 2026.</p>
          </div>
        </div>
      </section>

      <section className="on-paper bg-paper text-ink">
        <div className={`${band} items-start gap-7`}>
          <h2 className={`${display} text-[clamp(52px,8vw,96px)] leading-[0.92]`}>run it on your laptop.</h2>
          <CopyCommand command="docker-compose up --build" />
          <Link href="/start" className="text-xl font-bold">or try it right here →</Link>
        </div>
      </section>

      <footer className="border-t border-line bg-ink text-[#b9b7b0]">
        <div className="mx-auto flex max-w-[1280px] flex-wrap justify-between gap-3 px-5 py-8 text-base sm:px-10">
          <span>made by <a href="https://ayushh.in">ayush kumar</a></span>
          <a href={GITHUB}>github</a>
        </div>
      </footer>
    </div>
  );
}
