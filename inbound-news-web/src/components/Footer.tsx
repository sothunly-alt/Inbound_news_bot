import { CATEGORIES } from "@/lib/categories";

export function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer>
      <div className="container">
        <div className="footer-grid">
          <div className="footer-col">
            <div className="logo" style={{ fontSize: 32, marginBottom: 16 }}>
              Inbound Reports
            </div>
            <p style={{ color: "var(--text-secondary)", maxWidth: 400 }}>
              Independent technology journalism, published from Phnom Penh, Cambodia.
              Reporting the signal, not the noise.
            </p>
          </div>
          <div className="footer-col">
            <h4>Sections</h4>
            <ul>
              {CATEGORIES.map((c) => (
                <li key={c.slug}>
                  <a href={`/${c.slug}`}>{c.label}</a>
                </li>
              ))}
            </ul>
          </div>
          <div className="footer-col">
            <h4>How It Works</h4>
            <p style={{ color: "var(--text-secondary)", fontSize: 14, lineHeight: 1.6 }}>
              Inbound pulls live RSS feeds across tech, startups, and security,
              clusters related stories, and has AI rewrite them into short
              dispatches — posted to Telegram every 5am and 5pm, plus breaking
              alerts as they happen.
            </p>
          </div>
          <div className="footer-col">
            <h4>Sources</h4>
            <p style={{ color: "var(--text-secondary)", fontSize: 14, lineHeight: 1.6 }}>
              Every dispatch links back to its original reporting. Summaries
              are AI-generated for speed — we don&apos;t claim the original
              work. Open any story and use &quot;Read original source&quot; to
              go straight there.
            </p>
          </div>
        </div>
        <div className="footer-bottom">
          <div>© {year} Inbound Reports · Phnom Penh, Cambodia</div>
          <div>Built by the Inbound crew</div>
        </div>
      </div>
      <div className="footer-watermark">INBOUND</div>
    </footer>
  );
}
