"use client";

import { useState } from "react";

export function NewsletterForm() {
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitted(true);
  }

  if (submitted) {
    return <p style={{ color: "var(--accent)" }}>You&apos;re on the list.</p>;
  }

  return (
    <form className="newsletter-form" onSubmit={handleSubmit}>
      <input type="email" placeholder="you@somewhere.com" required />
      <button type="submit">Subscribe</button>
    </form>
  );
}
