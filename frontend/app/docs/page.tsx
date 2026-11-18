import Link from 'next/link';
import type { ReactNode } from 'react';
import { FEATURE_GLOSSARY } from '@/lib/glossary';

const CHAPTERS = [
  ['start', 'Start here'],
  ['basics', 'Market basics in 5 minutes'],
  ['quick', 'Quick start'],
  ['dashboard', 'A tour of the dashboard'],
  ['bots', 'The bots'],
  ['sim', 'How the simulator works'],
  ['signals', 'The warning signals'],
  ['scen', 'Scenarios'],
  ['reports', 'Session reports'],
  ['try', 'Things to try'],
  ['faq', 'Questions and fixes'],
  ['glossary', 'Glossary'],
  ['api', 'API'],
  ['limits', 'Safety and limitations'],
] as const;

/** A tiny order book for the worked example in chapter 2. */
const EXAMPLE_BOOK = {
  asks: [['100.03', '400'], ['100.02', '250'], ['100.01', '150']],
  bids: [['99.99', '200'], ['99.98', '300'], ['99.97', '500']],
};

const ORDER_TYPES = [
  ['Limit order', 'Buy or sell at a price you choose, or better. If nobody matches it right away it waits in the order book. Waiting orders are what make a market liquid.'],
  ['Market order', 'Buy or sell right now at whatever the best available price is. It always trades (if anyone is there), but you pay the spread and may move the price.'],
  ['Post-only', 'A limit order that is cancelled instead of trading immediately, so it only ever waits in the book. Market makers use it to make sure they earn the spread rather than pay it.'],
  ['IOC (immediate or cancel)', 'Trade whatever you can right now, cancel the rest. Nothing is left waiting in the book.'],
  ['Stop order', 'Dormant until the price reaches a trigger, then becomes a market order. Usually a stop-loss: "if it falls to X, get me out".'],
];

const PANELS: Array<[string, string]> = [
  ['Ticker tape', 'The scrolling strip along the top: price, spread, stress, depth, imbalance, VWAP and other headline numbers at a glance.'],
  ['Market summary', 'Eight tiles: mid price, spread, buy and sell depth, imbalance, volatility, VWAP and match rate. A note turns orange when a reading is unusual, for example depth below 60% of its median.'],
  ['Price chart', 'Candles of the mid price. Pick 1-second, 5-second or 1-minute candles. Each candle shows where the price opened, closed, and its high and low in that interval; light candles closed up, orange ones closed down. The panels under it plot spread and depth on the same timeline, so you can see a crunch line up with a price move.'],
  ['Order book · L2', 'The waiting orders, 8 levels a side: sell orders (asks, orange) above the mid, buy orders (bids) below. Size is shares at that price; cumulative is everything from the best price out to that level. The bar behind each row shows its size, and a level flagged by the large-order detector is highlighted.'],
  ['Liquidity stress', 'The big number is the stress score: the model\'s probability that a liquidity shock starts in the next 60 seconds. Under it are the four warning bands and every input the model reads, each with an i button that explains it. Orange inputs point towards stress.'],
  ['Large order detection', 'Inside the stress panel: when one price level is much bigger than the rest of the book, it shows the side, price, size, how many times the median level it is, its share of that side and a confidence score.'],
  ['Order flow', 'Whole-run counters (orders, fills, cancellations, match rate, notional value), the split of aggressive buying versus selling in the last 10 seconds, a 2-minute bar chart of that flow, and, when informed access is on, the hidden fundamental value and how far the market is from it.'],
  ['Activity', 'Three tabs. Agents: position, trades and profit for each bot type. Recent orders: the latest orders with their status. Event log: exchange events such as auctions, risk halts, scenario shocks and square-offs.'],
];

const AGENTS: Array<[string, string, string, number]> = [
  ['Market maker', 'Keeps a buy and a sell order at four price levels each side, around a size-weighted mid price. Leans its quotes away when it holds too much inventory, and widens them when the flow turns one-sided.', 'Supplies liquidity and earns the spread; real exchanges pay these firms to be there.', 3],
  ['High-frequency trader (HFT)', 'The fastest bot (1 μs). Reads the queue at the best price and joins the side that looks about to win. It never crosses the spread to get in, and gets out fast: on a 5-tick stop, after 90 seconds, or if the signal reverses.', 'Shows how speed and queue position, not prediction, make money in microstructure.', 2],
  ['Institutional', 'Has to buy or sell a big block, sliced into small child orders on a schedule (TWAP: time-weighted average price). Trades passively when on schedule, aggressively when behind.', 'Big funds move prices just by needing to trade; this is the main source of one-way pressure.', 2],
  ['Retail', 'Small, occasional orders driven by moving-average crossovers, with a stop-loss.', 'The everyday investor: small and slow.', 10],
  ['Informed', 'Gets an occasional noisy peek at the hidden fair value and trades when the gap beats its costs, aggressively if the gap is large. Only active with informed access on.', 'Information is an edge; these bots move the price towards fair value before the public catches up.', 3],
  ['Noise', 'Trades at random, more often after the price jumps, mostly with small orders at the best price.', 'Real markets have lots of trading with no clear reason; it keeps volume realistic.', 10],
  ['Liquidity trader', 'Has to complete a fixed quantity within the session whatever the price, sliced into child orders.', 'Forced flow, like a pension fund rebalancing or a margin call.', 1],
  ['Momentum', 'Buys breakouts above a recent range (and sells breakdowns), but only when aggressive flow confirms the move. Uses a trailing stop.', 'Trend followers amplify moves.', 2],
  ['Mean reversion', 'Bets that stretched prices snap back, using Bollinger bands and RSI, with a stop if the stretch keeps going.', 'The counterweight to momentum.', 2],
  ['Sentiment', 'Follows or fades the recent mood of the market and holds each position for a few minutes.', 'Herding behaviour.', 5],
  ['Spoofer', 'Places large orders it does not intend to fill, then cancels them, to make the book look one-sided. Only in the spoofing scenario.', 'Illegal in real markets; here to test the large-order detector.', 0],
];

const PHASES = [
  ['Pre-open', 'Market-open scenario only, the first 4% of the run. Orders collect but nothing trades; then a single auction price clears as much as possible.'],
  ['Open', 'Up to 10% of the run. Bots are 1.5 times as busy as usual, like the real opening rush.'],
  ['Continuous', 'The middle of the day. Normal matching, slightly quieter activity.'],
  ['Close', 'The last 10%. Activity picks up again.'],
  ['Square-off', 'The last 3%. Like a broker\'s intraday rule, every open position is closed at market, so the bots finish flat.'],
];

const FEATURE_GROUPS: Array<[string, string, string[]]> = [
  ['Right now', 'The state of the book this second, mostly against its normal over the last minute.', ['spread_ratio', 'depth_ratio', 'bid_depth_ratio', 'ask_depth_ratio', 'depth_change_1s', 'depth_change_5s', 'spread_change_5s', 'imbalance', 'top_imbalance', 'vol_ratio', 'flow_pressure']],
  ['Recent memory', 'What happened over the last minute or so: stress tends to come in clusters.', ['recent_stress', 'max_spread_ratio_10s', 'min_depth_ratio_10s', 'since_stress', 'depth_change_30s', 'max_spread_ratio_60s', 'min_depth_ratio_60s']],
  ['Long memory', 'The same ideas over 5 and 15 minutes, so the model knows when the last minute was unusually calm or busy.', ['stress_300s', 'stress_900s', 'spread_ratio_300s', 'spread_ratio_900s', 'depth_ratio_300s', 'depth_ratio_900s', 'baseline_vs_300s', 'vol_ratio_300s']],
  ['Book shape', 'Where the waiting orders sit across all 10 levels, not just how many there are.', ['near_share', 'span_ratio', 'depth_dist_ratio']],
  ['Activity', 'How restless the book and the trading are.', ['depth_volatility_10s', 'spread_vol_10s', 'abs_flow_30s']],
];

const BANDS = [
  ['safe', 'below 0.20', 'Nothing unusual. Trading costs are normal.', 'bg-paper-3'],
  ['caution', '0.20 – 0.40', 'Something is off: the book is thinning or the spread is twitchy. Worth watching.', 'bg-caution-paper'],
  ['warning', '0.40 – 0.60', 'A crunch is more likely than not to be building. Big orders would move the price a lot.', 'bg-accent'],
  ['critical', '0.60 and above', 'A shock is under way or imminent: the spread is blowing out or the book is emptying.', 'bg-ink text-fg'],
];

const SCENARIOS = [
  ['normal', 'Normal session', '1.0×', '1.0×', '1.0×', 'An ordinary day with every non-adversarial bot.', 'The baseline. The stress score should sit at safe almost all the time; use it to learn what calm looks like.'],
  ['market_open', 'Market open', '2.5×', '1.4×', '1.35×', 'Orders pile up before the open, one auction price clears them, then a wide, fast open.', 'The first minutes: no trades during pre-open, a jump at the auction, then spreads narrowing as the bots settle in.'],
  ['liquidity_shock', 'Liquidity shock', '1.0×', '1.0×', '1.0×', 'A normal book, then about a minute in, most waiting orders on one side are pulled and an aggressive order sweeps what is left. Liquidity returns over the next 20 seconds or so.', 'The stress score jumping to critical, depth collapsing, the spread blowing out, then the recovery. The clearest demo of what the warning is for.'],
  ['institutional_execution', 'Institutional execution', '1.25×', '1.2×', '1.15×', 'Twice as many institutional parent orders working through the day.', 'Persistent one-way flow in the order-flow panel and the institutions\' P&L in the agents table.'],
  ['volatility_spike', 'Volatility spike', '3.0×', '2.8×', '0.75×', 'A jumpier fair value, wider quotes, and two news shocks (one up, one down) that move fair value and hit the book at the same time.', 'Two sharp price moves and how fast the book refills after each.'],
  ['spoofing_stress', 'Spoofing stress', '1.75×', '1.5×', '0.9×', 'Spoofer bots switched on.', 'The large-order detector flagging levels that then vanish, and the cancellation count climbing.'],
  ['close_auction', 'Close / auction', '1.6×', '1.0×', '1.8×', 'A deeper book and more institutional activity towards a closing auction.', 'The busier close phase, the square-off at the end and the closing auction filling remaining positions.'],
];

const REPORT_PARTS = [
  ['Cover', 'Scenario, preset, seed and settings, a one-line verdict ("a calm session", "liquidity came under real strain") and six headline tiles.'],
  ['1 · Price', 'Candles for the whole run, the opening price as a dashed line, and triangles where the stress detector raised a warning.'],
  ['2 · Liquidity', 'Spread and depth over time with their medians, so a shock is easy to spot.'],
  ['3 · Summary', 'What happened, in six plain sentences.'],
  ['4 · Participants', 'Each bot type\'s trades, final position and profit or loss, with bars to compare at a glance.'],
  ['5 · Detectors', 'Every change of stress level with its score, plus a summary of the large orders flagged.'],
  ['6 · Market quality', 'Average and widest spread, trades per second, cancels per trade, volatility, price impact and slippage, each explained.'],
  ['7 · Record', 'Order-flow counts and how much data the report rests on.'],
  ['8 · Reference', 'A glossary and the method and limits.'],
];

const EXPERIMENTS = [
  ['See a crunch coming', 'Run Liquidity shock with the Balanced preset. Watch the stress panel for the first minute: which inputs turn orange first, and how high does the score go before depth actually collapses?'],
  ['Same day, different luck', 'Run Normal twice with seeds 1 and 2, then twice with seed 1. Seed 1 gives an identical run both times; seed 2 differs. Compare the reports.'],
  ['Who wins when it gets rough', 'Run Volatility spike, open the Agents tab, and compare market makers, HFTs and momentum traders with a Normal run.'],
  ['Catch a spoofer', 'Run Spoofing stress and watch Large order detection. Do flagged levels get traded, or cancelled before anyone reaches them?'],
  ['Information is an edge', 'Run Normal with informed access on, then off. Look at the informed traders\' P&L and the mispricing reading in Order flow.'],
];

const FAQ: Array<[string, ReactNode]> = [
  ['The dashboard is empty or says it is waiting.', <>The page needs the backend running and a session started. Start one from <Link href="/start">the start page</Link>. If you run locally, check the backend is on port 8000 (or whatever <code>NEXT_PUBLIC_API_URL</code> points to).</>],
  ['The stress panel says calibrating.', <>That is the fallback detector, used when the trained model file is missing. It needs about ten seconds of history before it can compare the book with its own normal.</>],
  ['Why is there a warning when the price looks calm?', <>The warning is about liquidity, not price. The price can sit still while the waiting orders thin out. Also, after an unusually quiet minute, even a return to normal spreads can count as a jump; the model knows this and raises caution early.</>],
  ['Why do almost all bots lose money?', <>Trading costs money: every time a bot crosses the spread it pays it, plus a small fee. The ones that wait for others to trade with them (market makers, HFTs) or that know something (informed traders) tend to come out ahead. That is how real markets work too.</>],
  ['Can I trust the profit numbers?', <>Only as a comparison between bots in this simulation. It is one synthetic run; nothing here says a strategy would make money in a real market.</>],
  ['Docker says the port is in use.', <>Another app holds port 3000 or 8000. Stop it, or run the backend with <code>--port 8765</code> and start the frontend with <code>NEXT_PUBLIC_API_URL=http://127.0.0.1:8765</code> and <code>NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8765</code>.</>],
];

const GLOSSARY = [
  ['Aggressor', 'The side of a trade that crossed the spread to trade immediately. It pays the spread; the waiting side earns it.'],
  ['Ask (offer)', 'A waiting sell order, or the lowest price someone is currently willing to sell at.'],
  ['Basis point (bp)', 'One hundredth of a percent: 0.01%. A 1 bp spread on a $100 stock is 1 cent.'],
  ['Bid', 'A waiting buy order, or the highest price someone is currently willing to pay.'],
  ['Candle (OHLC)', 'A summary of prices over an interval: open, high, low, close.'],
  ['Depth', 'Total shares waiting in the order book, here across the 10 best price levels on each side.'],
  ['Fill', 'A trade: a buyer and a seller matched.'],
  ['Fundamental value', 'The hidden fair price the simulation is built around. The public learns it 30 seconds late.'],
  ['Imbalance', '(buy depth − sell depth) / (buy depth + sell depth). −1 is all sellers, +1 all buyers.'],
  ['Inventory', 'The shares a trader currently holds. Market makers try to keep it near zero.'],
  ['Latency', 'How long an order takes to reach the exchange. 1 μs (a millionth of a second) for co-located HFTs, milliseconds for retail.'],
  ['Liquidity', 'How easily you can trade without moving the price: lots of waiting orders and a narrow spread.'],
  ['Liquidity shock', 'Here: the spread reaching 2.5 times its normal size, or depth falling to 40% of normal.'],
  ['Market maker', 'A trader that keeps orders on both sides of the book and earns the spread.'],
  ['Mid price', 'Halfway between the best bid and the best ask.'],
  ['P&L', 'Profit and loss. Realized is locked in by closing trades; unrealized is the value of open positions at the current price.'],
  ['Price-time priority', 'Matching rule: better prices trade first; at the same price, earlier orders trade first.'],
  ['Seed', 'The number that fixes the simulation\'s randomness. The same seed and settings give the same run.'],
  ['Slippage', 'How far your fill price ended up from the price when you sent the order.'],
  ['Spread', 'Best ask minus best bid: the cost of trading immediately.'],
  ['Tick', 'The smallest price step allowed, $0.01 here.'],
  ['VWAP', 'Volume-weighted average price: the average trade price weighted by size.'],
];

const API = [
  ['GET', '/api/health', 'Is the service up.'],
  ['GET', '/api/sandbox/presets', 'Bot populations you can choose from.'],
  ['GET', '/api/sandbox/scenarios', 'Scenario definitions and their multipliers.'],
  ['POST', '/api/sandbox/create', 'Start a run (preset, scenario, seed, latency, informed access, speed).'],
  ['PUT', '/api/sandbox/speed', 'Change the playback speed of the running session.'],
  ['POST', '/api/simulation/stop', 'Stop the run and freeze its report.'],
  ['GET', '/api/simulation/export', 'Download the full session record as JSON.'],
  ['GET', '/api/simulation/report', 'The frozen session report (JSON).'],
  ['GET', '/api/simulation/report.pdf', 'The same report as a PDF.'],
  ['WS', '/ws', 'Live feed: one market_update message per simulated second.'],
];

const h2 = 'm-0 font-display text-2xl font-semibold';
const h3 = 'm-0 mt-2 text-base font-bold';
const prose = 'm-0 max-w-[720px]';
const note = 'm-0 max-w-[720px] rounded-xl bg-paper-2 px-4 py-3 text-sm text-paper-fg2';

function Section({ id, n, title, children }: { id: string; n: number; title: string; children: ReactNode }) {
  return (
    <section id={id} className="flex scroll-mt-4 flex-col gap-3">
      <h2 className={h2}>{n}. {title}</h2>
      {children}
    </section>
  );
}

export default function DocsPage() {
  return (
    <div className="on-paper min-h-screen bg-paper text-[15px] leading-[1.65] text-ink">
      <header className="bg-ink text-fg">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-5">
            <Link href="/" className="inline-flex min-h-10 items-center font-display text-xl font-bold no-underline">SENTINEL</Link>
            <span className="text-fg-muted">Documentation</span>
          </div>
          <div className="flex gap-2">
            <a href="https://github.com/macayu17/sentinel" className="btn">GitHub</a>
            <Link href="/start" className="btn btn-accent">Open simulator</Link>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1200px] flex-wrap items-start gap-10 px-4 pb-[72px] pt-9 sm:px-6">
        <nav aria-label="Chapters" className="flex flex-[1_1_220px] flex-col gap-0.5 text-sm md:sticky md:top-4">
          <span className="px-3 pb-1.5 text-xs text-paper-muted">Contents</span>
          {CHAPTERS.map(([id, title], index) => (
            <a key={id} href={`#${id}`} className="flex min-h-9 items-center gap-2.5 rounded-lg px-3 font-medium no-underline hover:bg-paper-3">
              <span className="w-[18px] text-paper-muted">{index + 1}</span>{title}
            </a>
          ))}
        </nav>

        <main className="flex min-w-0 flex-[999_1_640px] flex-col gap-12">
          <section className="flex flex-col gap-2">
            <h1 className="m-0 font-display text-[40px] font-semibold leading-[1.1] tracking-[-0.02em]">Read the market. Then run it.</h1>
            <p className="m-0 max-w-[680px] text-[17px] text-paper-fg2">Everything you need to use SENTINEL, from what an order book is to how the warning model was trained. No finance background needed.</p>
          </section>

          <Section id="start" n={1} title="Start here">
            <p className={prose}>SENTINEL is a <strong>pretend stock market</strong> that runs on your computer. Forty trading bots, each with its own personality, buy and sell one made-up stock. While they trade, SENTINEL watches the market and <strong>warns you when it is about to run out of buyers or sellers</strong>: the moment when trading suddenly becomes expensive and prices jump. That moment is called a <em>liquidity crunch</em>, and in real markets it is when people lose the most money.</p>
            <p className={prose}>You can use it to learn how markets work, to watch a crunch happen safely, or to study how different kinds of traders behave under stress. Read chapter 2 if terms like <em>bid</em>, <em>spread</em> or <em>order book</em> are new; otherwise jump to <a href="#quick">the quick start</a>.</p>
            <p className={note}>Tip: on the dashboard, every number has a small <strong>i</strong> button next to it. Hover over it (or tap it on a phone) for a plain-language explanation.</p>
          </Section>

          <Section id="basics" n={2} title="Market basics in 5 minutes">
            <h3 className={h3}>The order book</h3>
            <p className={prose}>A stock exchange is a matchmaker. People who want to buy say what they will pay; people who want to sell say what they will accept. Orders that do not match straight away wait in a list called the <strong>order book</strong>. Here is a tiny one:</p>
            <div className="flex flex-wrap items-start gap-6">
              <div className="w-[260px] overflow-hidden rounded-xl bg-paper-2 text-sm">
                <div className="grid grid-cols-2 px-4 py-2 text-xs text-paper-muted"><span>Price</span><span className="text-right">Shares waiting</span></div>
                {EXAMPLE_BOOK.asks.map(([price, size]) => (
                  <div key={price} className="grid grid-cols-2 border-t border-paper-rule px-4 py-1.5"><span className="font-semibold text-accent-deep">{price}</span><span className="text-right">{size}</span></div>
                ))}
                <div className="border-y-2 border-ink px-4 py-1.5 text-center text-xs font-bold">mid 100.00 · spread 0.02</div>
                {EXAMPLE_BOOK.bids.map(([price, size]) => (
                  <div key={price} className="grid grid-cols-2 border-t border-paper-rule px-4 py-1.5"><span className="font-semibold">{price}</span><span className="text-right">{size}</span></div>
                ))}
              </div>
              <ul className="m-0 flex min-w-[260px] flex-1 list-disc flex-col gap-1.5 pl-5">
                <li>The top half are <strong>asks</strong>: people waiting to sell. The cheapest, 100.01, is the <strong>best ask</strong>.</li>
                <li>The bottom half are <strong>bids</strong>: people waiting to buy. The highest, 99.99, is the <strong>best bid</strong>.</li>
                <li>The gap between them, 0.02, is the <strong>spread</strong>. The point halfway, 100.00, is the <strong>mid price</strong>.</li>
                <li>All the shares waiting are the <strong>depth</strong>: 800 to sell and 1,000 to buy here.</li>
              </ul>
            </div>
            <h3 className={h3}>A worked example</h3>
            <p className={prose}>You want to buy 300 shares <em>right now</em>. You take the 150 at 100.01, then 150 of the 250 at 100.02. Your average price is 100.015, a bit above the mid: that extra is your cost of trading immediately. Now imagine most sellers had just cancelled and only 50 shares were waiting at each price. The same order would chew through several levels and pay far more. <strong>That is a liquidity crunch</strong>: nothing about the company changed, but trading suddenly got expensive. SENTINEL tries to see it coming.</p>
            <h3 className={h3}>Liquidity, in one line</h3>
            <p className={prose}>A market is <strong>liquid</strong> when lots of orders are waiting close to the current price, so trades barely move it. Narrow spread and deep book: liquid. Wide spread and thin book: illiquid, and dangerous.</p>
            <h3 className={h3}>Kinds of orders</h3>
            <dl className="m-0 grid gap-2.5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))' }}>
              {ORDER_TYPES.map(([term, meaning]) => (
                <div key={term} className="rounded-xl bg-paper-2 px-4 py-3.5"><dt className="font-bold">{term}</dt><dd className="m-0 mt-1 text-sm text-paper-fg2">{meaning}</dd></div>
              ))}
            </dl>
          </Section>

          <Section id="quick" n={3} title="Quick start">
            <ol className="m-0 flex max-w-[720px] list-decimal flex-col gap-2 pl-5">
              <li><strong>Open the simulator.</strong> Click <Link href="/start">Open simulator</Link> (or <em>try it</em> on the home page).</li>
              <li><strong>Choose a preset</strong>, the mix of bots. <em>Balanced</em> (40 bots of every non-adversarial type) is the best first run.</li>
              <li><strong>Choose a scenario</strong>, the kind of day. Start with <em>Normal session</em> to learn what calm looks like, then try <em>Liquidity shock</em> to see a crunch.</li>
              <li><strong>Leave the rest on default</strong> for now. The seed fixes the randomness (same seed, same run); latency sets how fast orders travel; informed access lets some bots peek at the hidden fair value; speed is how fast the replay runs.</li>
              <li><strong>Launch.</strong> The dashboard fills in within a second or two and updates every simulated second.</li>
              <li><strong>Stop when you like</strong> (or let it run to the close). Stopping freezes a session report you can read on screen or download as PDF or JSON.</li>
            </ol>
            <h3 className={h3}>Running it on your own computer</h3>
            <p className={prose}>With Docker installed, one command starts everything:</p>
            <pre className="m-0 overflow-x-auto rounded-xl bg-ink px-4 py-3.5 font-mono text-[13px] text-fg">{`docker-compose up --build
# dashboard  http://localhost:3000
# api        http://localhost:8000   ·   live feed ws://localhost:8000/ws`}</pre>
            <p className={prose}>Without Docker, start the backend (Python 3.11) and the frontend (Node 18+) in two terminals:</p>
            <pre className="m-0 overflow-x-auto rounded-xl bg-ink px-4 py-3.5 font-mono text-[13px] text-fg">{`# terminal 1
cd backend
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8000

# terminal 2
cd frontend
npm install
npm run dev        # then open http://localhost:3000`}</pre>
          </Section>

          <Section id="dashboard" n={4} title="A tour of the dashboard">
            <p className={prose}>Everything on the dashboard updates once per simulated second. Here is what each part shows, top to bottom. Remember the <strong>i</strong> buttons: each one explains its number in place.</p>
            <dl className="m-0 flex max-w-[760px] flex-col gap-2.5">
              {PANELS.map(([name, about]) => (
                <div key={name} className="rounded-xl bg-paper-2 px-4 py-3.5"><dt className="font-bold">{name}</dt><dd className="m-0 mt-1 text-sm text-paper-fg2">{about}</dd></div>
              ))}
            </dl>
            <p className={note}>Session times use a pretend clock that opens at 09:30, like the New York stock exchange, so 09:31:00 means one minute into the run.</p>
          </Section>

          <Section id="bots" n={5} title="The bots">
            <p className={prose}>Each bot follows fixed rules; there is no hidden AI trading. They are modelled on the kinds of participants found in real stock markets, and all of them obey the same risk rules: a cap on how much they can hold, and a kill switch that stops a bot opening new positions after a large loss (it shows as halted in the Agents tab).</p>
            <div className="overflow-x-auto rounded-xl bg-paper-2">
              <table className="w-full min-w-[720px] border-collapse text-sm">
                <thead><tr className="text-left text-xs text-paper-muted"><th scope="col" className="px-3.5 py-2.5 font-medium">Bot</th><th scope="col" className="p-2.5 font-medium">What it does</th><th scope="col" className="p-2.5 font-medium">Why it is there</th><th scope="col" className="px-3.5 py-2.5 text-right font-medium">In Balanced</th></tr></thead>
                <tbody>
                  {AGENTS.map(([name, does, why, count]) => (
                    <tr key={name} className="border-t border-paper-rule align-top"><td className="px-3.5 py-2.5 font-semibold">{name}</td><td className="px-2.5 py-2.5 text-paper-fg2">{does}</td><td className="px-2.5 py-2.5 text-paper-fg2">{why}</td><td className="px-3.5 py-2.5 text-right">{count}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="sim" n={6} title="How the simulator works">
            <h3 className={h3}>One second at a time</h3>
            <p className={prose}>The simulation moves in steps of one simulated second. Within a second, each bot wakes up on its own schedule, looks at the market as it stood when its data last arrived (slow bots see older data), and may send, change or cancel orders. Orders take time to reach the exchange, from 1 microsecond for the fastest bot to milliseconds for retail.</p>
            <h3 className={h3}>Matching</h3>
            <p className={prose}>The exchange uses <strong>price-time priority</strong>, like real stock exchanges: the best price trades first, and among orders at the same price, the one that arrived first trades first. That is why speed matters for HFTs: being early in the queue at the best price is how they get filled.</p>
            <h3 className={h3}>The hidden fair value</h3>
            <p className={prose}>Underneath the market is a hidden <strong>fundamental value</strong> that drifts gently, with an occasional jump for news. Informed bots get a noisy early look at it; everyone else learns it 30 seconds later. Arbitrage traders then pull the price back towards that public value, so prices wander like a real stock but cannot drift off forever. Its volatility is set to about 20% a year, in line with large real stocks.</p>
            <h3 className={h3}>The venue&apos;s own orders</h3>
            <p className={prose}>Real books have thousands of small passive traders. SENTINEL stands in for them with a ten-level ladder of waiting orders around the public fair value, topped up by a fifth of its size every second. A big sweep thins it for a few seconds rather than for good, and forced selling at the close meets fair-value buyers instead of an empty book.</p>
            <h3 className={h3}>The trading day</h3>
            <div className="overflow-x-auto rounded-xl bg-paper-2">
              <table className="w-full min-w-[560px] border-collapse text-sm">
                <tbody>
                  {PHASES.map(([phase, about]) => (
                    <tr key={phase} className="border-t border-paper-rule first:border-t-0"><td className="w-[130px] px-3.5 py-2 font-semibold">{phase}</td><td className="px-2.5 py-2 text-paper-fg2">{about}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3 className={h3}>How realistic is it?</h3>
            <p className={prose}>It was tuned against five real NASDAQ trading days (see chapter 7). In normal sessions the price moves about 17–21% a year (real large stocks: 13–20%), stays within about 25 bps of fair value, and the book hits the liquidity-shock condition 2.5–6% of the time (real: 0–13%). Short-term price moves have the &ldquo;fat tails&rdquo; real markets show. It is still a model: one stock, no real news, and bots instead of people.</p>
            <p className={note}>A fixed seed reproduces a run exactly: same seed, same settings, same result.</p>
          </Section>

          <Section id="signals" n={7} title="The warning signals">
            <h3 className={h3}>Liquidity stress: what it predicts</h3>
            <p className={prose}>The stress score is a probability between 0 and 1: how likely it is that <strong>within the next 60 seconds</strong> the spread reaches 2.5 times its normal size, or the waiting orders fall to 40% of normal. &ldquo;Normal&rdquo; means the typical level over the last calm minute. Health is simply 1 minus stress.</p>
            <div className="grid max-w-[760px] gap-1.5 sm:grid-cols-2 lg:grid-cols-4">
              {BANDS.map(([level, range, meaning, tone]) => (
                <div key={level} className={`flex flex-col gap-1 rounded-[10px] px-3 py-2.5 ${tone}`}><strong>{level}</strong><span className="text-[13px] opacity-80">{range}</span><span className="text-[13px]">{meaning}</span></div>
              ))}
            </div>
            <h3 className={h3}>What the model reads</h3>
            <p className={prose}>Every second the model reads 32 numbers about the book. Most are written as <em>today versus normal</em>, so 1.00 means normal; that way the same model works for a $100 simulated stock and a $580 real one. They fall into five groups:</p>
            <div className="flex flex-col gap-3">
              {FEATURE_GROUPS.map(([group, about, keys]) => (
                <details key={group} className="rounded-xl bg-paper-2 px-4 py-3">
                  <summary className="cursor-pointer font-bold">{group} <span className="font-normal text-paper-muted">· {keys.length} inputs</span></summary>
                  <p className="m-0 mt-1 text-sm text-paper-muted">{about}</p>
                  <dl className="m-0 mt-2 flex flex-col gap-2">
                    {keys.map((key) => (
                      <div key={key} className="border-t border-paper-rule pt-2 text-sm">
                        <dt><code>{key}</code> <span className="font-semibold">· {FEATURE_GLOSSARY[key]?.name}</span></dt>
                        <dd className="m-0 mt-0.5 text-paper-fg2">{FEATURE_GLOSSARY[key]?.info}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              ))}
            </div>
            <h3 className={h3}>How the model was built</h3>
            <p className={prose}>It learned from <strong>real market data</strong>: five full trading days of NASDAQ order books from LOBSTER (Apple, Amazon, Google, Intel and Microsoft, 21 June 2012), replayed one second at a time, plus 28 simulated sessions given a quarter of the weight. The model is LightGBM, a fast &ldquo;gradient-boosted trees&rdquo; method that combines thousands of small yes/no rules; here it is kept deliberately small (7 leaves per tree, 2,000 trees) so it generalises instead of memorising. Its raw scores are then calibrated, so that a reading of 0.30 really does mean about a 30% chance. The live dashboard computes the inputs with exactly the same code used in training.</p>
            <h3 className={h3}>How good is it?</h3>
            <p className={prose}>To test it honestly, each stock was scored by a version of the model that never saw that stock. The score used is <strong>ROC-AUC</strong>: if you pick one moment just before a real crunch and one calm moment at random, it is the chance the model rated the crunch moment as riskier. 0.5 is a coin flip and 1.0 is perfect.</p>
            <div className="overflow-x-auto rounded-xl bg-paper-2">
              <table className="w-full min-w-[520px] border-collapse text-sm">
                <thead><tr className="text-left text-xs text-paper-muted"><th scope="col" className="px-3.5 py-2.5 font-medium">Tested on</th><th scope="col" className="p-2.5 text-right font-medium">ROC-AUC</th><th scope="col" className="px-3.5 py-2.5 text-right font-medium">Average precision</th></tr></thead>
                <tbody>
                  <tr className="border-t border-paper-rule"><td className="px-3.5 py-2">Real stocks it never saw (average)</td><td className="px-2.5 py-2 text-right font-semibold">0.89</td><td className="px-3.5 py-2 text-right font-semibold">0.61</td></tr>
                  <tr className="border-t border-paper-rule"><td className="px-3.5 py-2">Simple rule: only today&apos;s spread and depth</td><td className="px-2.5 py-2 text-right">0.70</td><td className="px-3.5 py-2 text-right">0.36</td></tr>
                  <tr className="border-t border-paper-rule"><td className="px-3.5 py-2">Simulated sessions it never saw</td><td className="px-2.5 py-2 text-right">0.77</td><td className="px-3.5 py-2 text-right">0.55</td></tr>
                </tbody>
              </table>
            </div>
            <p className={prose}>Average precision measures how often a raised warning is right, weighted across all thresholds; higher is better, and it depends on how rare crunches are. Logistic regression, random forests, XGBoost, larger LightGBM models and ensembles were all tried and scored lower. One honest caveat: part of the gain comes from the 5 and 15 minute memory. After an unusually calm minute, even a return to normal spreads counts as a crunch under the definition above, and the model learns to expect it.</p>
            <p className={note}>Without the trained model file, the backend falls back to <code>adaptive_stress</code>: a simple comparison of the current book with its own recent history. It reports <code>calibrating</code> for the first few seconds.</p>
            <h3 className={h3}>Large order detection</h3>
            <p className={prose}>Separately, SENTINEL scans the visible book for one price level that is far bigger than the rest (pattern <code>large_level</code>). It could be a big fund parking an order, or a spoofer showing size it will cancel. Each flag reports the side, price, estimated size, how many times the median level it is, its share of that side, and a confidence from 0 to 1.</p>
            <p className="m-0 max-w-[720px] rounded-xl bg-ink px-4 py-3.5 text-fg">Read signals as evidence, not instructions. A good habit: when a signal moves, find the change in orders, depth or flow that moved it.</p>
          </Section>

          <Section id="scen" n={8} title="Scenarios">
            <p className={prose}>A scenario changes the conditions of the day. The three multipliers scale the normal quoted spread, the fair value&apos;s volatility and the depth of the venue&apos;s waiting orders.</p>
            <div className="overflow-x-auto rounded-xl bg-paper-2">
              <table className="w-full min-w-[820px] border-collapse text-sm">
                <thead><tr className="text-left text-xs text-paper-muted"><th scope="col" className="px-3.5 py-2.5 font-medium">Scenario</th><th scope="col" className="p-2.5 text-right font-medium">Spread</th><th scope="col" className="p-2.5 text-right font-medium">Vol.</th><th scope="col" className="p-2.5 text-right font-medium">Depth</th><th scope="col" className="p-2.5 font-medium">What happens</th><th scope="col" className="px-3.5 py-2.5 font-medium">What to watch</th></tr></thead>
                <tbody>
                  {SCENARIOS.map(([key, label, spread, vol, depth, about, watch]) => (
                    <tr key={key} className="border-t border-paper-rule align-top"><td className="px-3.5 py-2.5"><strong>{label}</strong><br /><code className="text-xs">{key}</code></td><td className="px-2.5 py-2.5 text-right">{spread}</td><td className="px-2.5 py-2.5 text-right">{vol}</td><td className="px-2.5 py-2.5 text-right">{depth}</td><td className="px-2.5 py-2.5 text-paper-fg2">{about}</td><td className="px-3.5 py-2.5 text-paper-fg2">{watch}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="reports" n={9} title="Session reports">
            <p className={prose}>Stopping a run, or letting it reach the close, freezes its final state into a report. Read it on screen, download the <strong>PDF</strong> to keep or share, or download the <strong>JSON</strong> for your own analysis (it holds every recorded second, order, trade and event). The PDF has nine parts:</p>
            <dl className="m-0 grid max-w-[760px] gap-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))' }}>
              {REPORT_PARTS.map(([part, about]) => (
                <div key={part} className="rounded-xl bg-paper-2 px-4 py-3"><dt className="font-bold">{part}</dt><dd className="m-0 mt-0.5 text-sm text-paper-fg2">{about}</dd></div>
              ))}
            </dl>
            <Link href="/dashboard/session-report" className="btn self-start bg-ink text-fg">Open the latest report</Link>
          </Section>

          <Section id="try" n={10} title="Things to try">
            <ol className="m-0 flex max-w-[720px] list-decimal flex-col gap-2 pl-5">
              {EXPERIMENTS.map(([title, body]) => <li key={title}><strong>{title}.</strong> {body}</li>)}
            </ol>
          </Section>

          <Section id="faq" n={11} title="Questions and fixes">
            <div className="flex max-w-[760px] flex-col gap-2">
              {FAQ.map(([question, answer]) => (
                <details key={question} className="rounded-xl bg-paper-2 px-4 py-3">
                  <summary className="cursor-pointer font-bold">{question}</summary>
                  <p className="m-0 mt-1.5 text-sm text-paper-fg2">{answer}</p>
                </details>
              ))}
            </div>
          </Section>

          <Section id="glossary" n={12} title="Glossary">
            <dl className="m-0 grid gap-x-6 gap-y-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))' }}>
              {GLOSSARY.map(([term, meaning]) => (
                <div key={term} className="border-t border-paper-rule pt-2"><dt className="font-bold">{term}</dt><dd className="m-0 text-sm text-paper-fg2">{meaning}</dd></div>
              ))}
            </dl>
          </Section>

          <Section id="api" n={13} title="API">
            <p className={prose}>For developers: the dashboard talks to the backend through this REST API and one WebSocket. Interactive API docs are served at <code>/docs</code> on the backend.</p>
            <div className="overflow-hidden rounded-xl bg-paper-2">
              {API.map(([method, path, about]) => (
                <div key={path} className="grid grid-cols-[52px_1fr] gap-x-3 gap-y-1 border-t border-paper-rule px-3.5 py-2.5 text-sm first:border-t-0 sm:grid-cols-[60px_240px_1fr]">
                  <span className="font-bold text-accent-deep">{method}</span>
                  <code className="justify-self-start">{path}</code>
                  <span className="col-span-2 text-paper-fg2 sm:col-span-1">{about}</span>
                </div>
              ))}
            </div>
          </Section>

          <section id="limits" className="flex scroll-mt-4 flex-col gap-2.5 rounded-panel bg-ink px-6 py-[22px] text-fg">
            <h2 className={h2}>14. Safety and limitations</h2>
            <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-fg-2">
              <li>Everything here is simulated: prices, trades and profits are synthetic.</li>
              <li>Warnings are research signals, not investment advice.</li>
              <li>The model was trained on five days of 2012 data for five large US stocks; other markets and periods may behave differently.</li>
              <li>Results depend on the scenario, seed, bot mix, latency and run length. Repeat runs before drawing conclusions.</li>
            </ul>
          </section>
        </main>
      </div>
    </div>
  );
}
