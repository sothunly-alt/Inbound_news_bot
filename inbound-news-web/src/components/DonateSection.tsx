import Image from "next/image";

export function DonateSection() {
  return (
    <section className="newsletter" id="support">
      <div className="container">
        <h2>Keep the Wire Running.</h2>
        <p>
          Inbound is free to read, no paywall, no ads. If it&apos;s useful to
          you, scan the KHQR code to send whatever you&apos;d like — that&apos;s
          the only funding this runs on.
        </p>
        <div
          style={{
            display: "inline-flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 16,
            background: "var(--bg)",
            padding: 24,
            border: "1px solid var(--border)",
          }}
        >
          <Image
            src="/khqr.png"
            alt="Scan to donate via KHQR"
            width={280}
            height={280}
            style={{ width: 280, height: 280, objectFit: "contain" }}
          />
          <span
            className="mono"
            style={{ fontSize: 12, textTransform: "uppercase", color: "var(--text-primary)" }}
          >
            Scan with any KHQR-supported app
          </span>
        </div>
      </div>
    </section>
  );
}
