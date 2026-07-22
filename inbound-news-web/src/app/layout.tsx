import type { Metadata } from "next";
import { Source_Serif_4, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/Header";
import { Ticker } from "@/components/Ticker";
import { Footer } from "@/components/Footer";

// "Jacquarda Bastian 9" (the logotype face from the original design) isn't
// available through next/font/google's type-checked font list, so it's
// loaded the same way the original mock did: a direct Google Fonts <link>
// below. Source Serif 4 and JetBrains Mono are self-hosted via next/font.
const serif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-serif",
  weight: ["400", "600", "700"],
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  title: "Inbound Reports — Tech, filed from the ground up.",
  description:
    "Independent technology journalism from Phnom Penh — startups, AI, cybersecurity, and more.",
};

// Runs before paint so the site never flashes the wrong theme on load.
const themeInitScript = `
(function() {
  try {
    var saved = localStorage.getItem('theme');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var theme = saved || (prefersDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="light" className={`${serif.variable} ${mono.variable}`}>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Jacquarda+Bastian+9&display=swap"
          rel="stylesheet"
        />
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Header />
        <Ticker />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
