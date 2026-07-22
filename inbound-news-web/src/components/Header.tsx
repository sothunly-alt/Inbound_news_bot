import Link from "next/link";
import { ThemeToggle } from "./ThemeToggle";
import { CATEGORIES } from "@/lib/categories";

export function Header() {
  return (
    <header>
      <div className="container">
        <div className="header-top">
          <Link href="/" className="logo" style={{ textDecoration: "none" }}>
            Inbound Reports
          </Link>
          <div className="utility-nav">
            <ThemeToggle />
            <button className="btn">EN / KM</button>
            <Link href="/#support" className="btn btn-primary" style={{ display: "inline-block" }}>
              Donate
            </Link>
          </div>
        </div>
        <nav className="main-nav">
          {CATEGORIES.map((c) => (
            <Link key={c.slug} href={`/${c.slug}`}>
              {c.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
