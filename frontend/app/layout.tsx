import type { Metadata, Viewport } from 'next';
import { Funnel_Display, Funnel_Sans } from 'next/font/google';
import './globals.css';

const display = Funnel_Display({ subsets: ['latin'], weight: ['500', '600', '700', '800'], variable: '--font-display' });
const sans = Funnel_Sans({ subsets: ['latin'], weight: ['400', '500', '600', '700'], variable: '--font-sans' });

export const metadata: Metadata = {
  title: 'SENTINEL — market microstructure simulator',
  description: 'A multi-agent order-book simulator that warns before liquidity runs out.',
};

export const viewport: Viewport = { themeColor: '#111114' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${sans.variable}`} data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
