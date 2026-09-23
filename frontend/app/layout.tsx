import type { Metadata } from 'next';
import './globals.css';
import './public-theme.css';

export const metadata: Metadata = {
  title: 'SENTINEL — Market Microstructure Early Warning System',
  description:
    'Smart Early-warning Network for Trading, Institutional orders, and Liquidity Events. Real-time order book simulation with ML-powered liquidity shock prediction.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: `try { const theme = localStorage.getItem('sentinel-theme') === 'dark' ? 'dark' : 'light'; document.documentElement.classList.toggle('theme-dark', theme === 'dark'); document.documentElement.classList.toggle('theme-light', theme === 'light'); } catch {}` }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      </head>
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
