/**
 * Plain-language explanations for every number the dashboard shows.
 * `alarm` says which direction of a stress feature means trouble.
 */

export type GlossaryEntry = {
  /** Human name, shown as the tooltip heading. */
  name: string;
  /** What it is and how to read it, written for a first-time reader. */
  info: string;
  /** True when this reading points at stress. */
  alarm?: (value: number) => boolean;
};

const above = (limit: number) => (v: number) => v > limit;
const below = (limit: number) => (v: number) => v < limit;
const beyond = (limit: number) => (v: number) => Math.abs(v) > limit;

/** Inputs to the liquidity-stress model (and the fallback detector). */
export const FEATURE_GLOSSARY: Record<string, GlossaryEntry> = {
  spread_ratio: { name: 'Spread vs normal', alarm: above(1.5), info: 'The gap between the best buy and best sell price, divided by its usual size over the last minute. 1.00 is normal; 2.00 means the gap has doubled, so trading right now costs twice as much.' },
  depth_ratio: { name: 'Depth vs normal', alarm: below(0.6), info: 'How many shares are waiting to be traded in the book, compared with the usual amount over the last minute. 1.00 is normal; 0.50 means half the usual liquidity has gone.' },
  bid_depth_ratio: { name: 'Buy-side depth vs normal', alarm: below(0.6), info: 'Same as depth vs normal, for buy orders only. A low value means few buyers are waiting, so sellers will push the price down easily.' },
  ask_depth_ratio: { name: 'Sell-side depth vs normal', alarm: below(0.6), info: 'Same as depth vs normal, for sell orders only. A low value means few sellers are waiting, so buyers will push the price up easily.' },
  depth_change_1s: { name: 'Depth change, 1 s', alarm: below(0.7), info: 'Depth now divided by depth one second ago. Below 1.00 means orders are disappearing; a sudden drop is often the first sign of a crunch.' },
  depth_change_5s: { name: 'Depth change, 5 s', alarm: below(0.6), info: 'Depth now divided by depth five seconds ago. Smooths out one-second noise to show whether liquidity is steadily draining.' },
  spread_change_5s: { name: 'Spread change, 5 s', alarm: above(1.5), info: 'Spread now divided by the spread five seconds ago. Above 1.00 means the gap between buyers and sellers is widening.' },
  imbalance: { name: 'Book imbalance', alarm: beyond(0.4), info: 'Buy depth minus sell depth, divided by the total, across all 10 levels. Runs from −1 (only sellers) to +1 (only buyers); 0 is balanced. A one-sided book breaks more easily.' },
  top_imbalance: { name: 'Best-price imbalance', alarm: beyond(0.6), info: 'The same imbalance, but only for the orders at the best buy and best sell price. A queue about to run out on one side often predicts the next price move.' },
  vol_ratio: { name: 'Volatility vs normal', alarm: above(2), info: 'How much the price has been jumping over the last 10 seconds, compared with the usual amount over the last minute. Above 2 means the market is unusually jumpy.' },
  flow_pressure: { name: 'Flow pressure', alarm: beyond(0.5), info: 'Shares bought aggressively minus shares sold aggressively in the last 10 seconds, relative to the depth in the book. Strong one-way flow eats through the waiting orders.' },
  recent_stress: { name: 'Stress in last minute', alarm: above(0.2), info: 'Share of the last 60 seconds the book spent in a stressed state (spread above 2.5× normal or depth below 40% of normal). 0 is calm; 1 is stressed the whole minute.' },
  max_spread_ratio_10s: { name: 'Widest spread, 10 s', alarm: above(2.5), info: 'The highest "spread vs normal" reading in the last 10 seconds. Catches brief spikes the current reading may already have missed.' },
  min_depth_ratio_10s: { name: 'Thinnest depth, 10 s', alarm: below(0.5), info: 'The lowest "depth vs normal" reading in the last 10 seconds. Catches brief holes in the book.' },
  since_stress: { name: 'Time since stress', alarm: below(0.2), info: 'How long since the book was last stressed, scaled so 1.00 means five minutes or more. High is good: it has been calm. Low means trouble happened very recently, and stress tends to come back.' },
  depth_change_30s: { name: 'Depth change, 30 s', alarm: below(0.6), info: 'Depth now divided by depth 30 seconds ago. Shows slower drains that the 1 s and 5 s readings smooth over.' },
  max_spread_ratio_60s: { name: 'Widest spread, 60 s', alarm: above(2.5), info: 'The highest "spread vs normal" reading over the last minute.' },
  min_depth_ratio_60s: { name: 'Thinnest depth, 60 s', alarm: below(0.4), info: 'The lowest "depth vs normal" reading over the last minute.' },
  stress_300s: { name: 'Stress in last 5 min', alarm: above(0.1), info: 'Share of the last five minutes spent in a stressed state. A market that has been stressed recently is more likely to be stressed again.' },
  stress_900s: { name: 'Stress in last 15 min', alarm: above(0.1), info: 'Share of the last fifteen minutes spent in a stressed state. The long-memory version of the line above.' },
  spread_ratio_300s: { name: 'Spread vs 5-min normal', alarm: above(1.5), info: 'Spread now compared with its typical size over the last five minutes, a slower and steadier baseline than the one-minute one.' },
  spread_ratio_900s: { name: 'Spread vs 15-min normal', alarm: above(1.5), info: 'Spread now compared with its typical size over the last fifteen minutes.' },
  depth_ratio_300s: { name: 'Depth vs 5-min normal', alarm: below(0.6), info: 'Depth now compared with its typical level over the last five minutes.' },
  depth_ratio_900s: { name: 'Depth vs 15-min normal', alarm: below(0.6), info: 'Depth now compared with its typical level over the last fifteen minutes.' },
  baseline_vs_300s: { name: 'Calm vs 5-min normal', alarm: below(0.6), info: 'The one-minute "normal" spread divided by the five-minute one. Below 1.00 means the last minute was unusually calm, so even a return to an ordinary spread will look like a jump against the short baseline.' },
  vol_ratio_300s: { name: 'Volatility vs 5-min normal', alarm: above(2), info: 'Price jumpiness over the last 10 seconds compared with the last five minutes.' },
  near_share: { name: 'Depth near the best price', alarm: below(0.15), info: 'Share of all visible orders that sit in the three best price levels on each side. Low means the liquidity is parked far from the current price, so a trade moves the price a lot before it finds it.' },
  span_ratio: { name: 'Book width vs normal', alarm: above(1.5), info: 'Distance from the lowest to the highest of the 10 visible price levels, compared with the last minute. A wider book means the same number of orders is spread thinner across prices.' },
  depth_dist_ratio: { name: 'Depth distance vs normal', alarm: above(1.5), info: 'Average distance of the waiting orders from the mid price, weighted by size, compared with the last minute. Rising means liquidity is backing away.' },
  depth_volatility_10s: { name: 'Depth jumpiness, 10 s', alarm: above(0.3), info: 'How much total depth has been jumping from second to second over the last 10 seconds. Large values mean orders are flickering in and out.' },
  spread_vol_10s: { name: 'Spread jumpiness, 10 s', alarm: above(0.5), info: 'How much "spread vs normal" has been jumping over the last 10 seconds.' },
  abs_flow_30s: { name: 'Trading intensity, 30 s', alarm: above(0.5), info: 'Average size of aggressive trading (buys and sells, ignoring direction) over the last 30 seconds, relative to the book. Busy markets use up liquidity faster.' },
  // Fallback detector (no trained model loaded).
  depth_depletion: { name: 'Depth depletion', alarm: above(0.5), info: 'How far visible depth has fallen below its trailing normal, from 0 (none) to 1 (gone).' },
  spread_expansion: { name: 'Spread expansion', alarm: above(0.5), info: 'How far the spread has widened beyond its trailing normal, scaled 0 to 1.' },
  volatility_expansion: { name: 'Volatility expansion', alarm: above(0.5), info: 'How far recent price volatility has risen above its trailing normal, scaled 0 to 1.' },
  order_flow_pressure: { name: 'Order-flow pressure', alarm: above(0.5), info: 'How one-sided recent aggressive trading has been, scaled 0 to 1.' },
};

/** Every other labelled number on the dashboard. */
export const TERM_GLOSSARY: Record<string, string> = {
  // Liquidity stress
  'Stress score': 'The model\'s probability (0 to 1) that within the next 60 seconds the spread will reach 2.5× normal or the depth will fall to 40% of normal. It is computed every simulated second.',
  Health: 'One minus the stress score. 1.00 is perfectly healthy, 0 is a crunch in progress.',
  'Warning level': 'The stress score in bands: safe below 0.20, caution 0.20–0.40, warning 0.40–0.60, critical above 0.60.',
  // Large orders
  'Side · price': 'Which side the unusually large resting order is on (BUY or SELL) and its price level.',
  'Est. size': 'Number of shares resting at that price level.',
  'Size multiple': 'How many times larger this level is than the median level in the visible book.',
  'Depth share': 'What fraction of all visible orders on that side sit at this one level.',
  Confidence: 'How sure the detector is that this is a genuinely outsized order (0 to 1), based on how far it stands out.',
  Pattern: 'The rule that fired. large_level means one visible price level is far bigger than the rest.',
  // Market summary
  'Mid price': 'Halfway between the best buy price and the best sell price. The change shown is since the session started.',
  Spread: 'The gap between the best sell price and the best buy price, in basis points (1 bp = 0.01%). It is the cost of trading immediately. Tick = the smallest allowed price step, $0.01.',
  'Bid depth': 'Total shares waiting to buy across the 10 best price levels. The note compares it with the session median.',
  'Ask depth': 'Total shares waiting to sell across the 10 best price levels. The note compares it with the session median.',
  Imbalance: 'Bid depth minus ask depth, divided by the total: −1 is all sellers, +1 all buyers, 0 balanced.',
  Volatility: 'How much the price has been moving, scaled to a yearly figure so it compares with quoted stock volatility (large US stocks are typically 15–30%).',
  VWAP: 'Volume-weighted average price: the average price of every trade this session, weighted by size. Estimated from the trades the dashboard has seen.',
  'Match rate': 'Share of submitted orders that traded at least partly. The rest are still waiting, cancelled or expired.',
  // Order flow
  'Orders submitted': 'Every order any bot has sent to the exchange this session.',
  Fills: 'Number of trades: each time a buyer and a seller were matched.',
  Cancellations: 'Orders withdrawn before they traded, mostly bots updating their quotes.',
  'Submitted notional': 'Total dollar value of all submitted orders (price × shares).',
  Activity: 'How busy the bots are relative to the middle of the day: the open and close run hotter than 1×, midday cooler.',
  'Fundamental value': 'The hidden "true" price the simulation is built around. Informed bots see it early; everyone else learns it 30 seconds late.',
  Mispricing: 'How far the market price is from the fundamental value, in basis points. Positive means the market is above it.',
  'Oracle noise σ': 'How noisy an informed bot\'s private read of the fundamental value is.',
  'Aggressor volume': 'Shares traded by orders that crossed the spread to trade immediately. Buy aggressors lift sellers; sell aggressors hit buyers.',
  // Order book
  Price: 'The price level. Sell orders (asks) are above the mid, buy orders (bids) below.',
  Size: 'Shares resting at this price level.',
  Cumulative: 'Shares from the best price out to this level: how many you could trade before reaching this price.',
  // Agents
  'Agent type': 'The kind of trading bot. Each type follows its own rules; see the docs for what each one does.',
  Count: 'How many bots of this type are in the session.',
  'Net position': 'Shares held right now, summed over the bots of this type. Positive is long (owns shares), negative is short.',
  Trades: 'Number of fills these bots took part in.',
  'Realized PnL': 'Profit or loss already locked in by closing positions, after fees, in dollars.',
  'Unrealized PnL': 'Profit or loss on positions still open, valued at the current price.',
  'Total PnL': 'Realized plus unrealized profit or loss.',
  Status: 'active, or halted: a bot that lost more than its drawdown limit can only close positions, not open new ones.',
};
