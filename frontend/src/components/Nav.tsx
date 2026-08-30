import "./Nav.css";
import { SCREENS } from "../lib/screens";

/**
 * Sticky top nav, shared by every screen and the landing page alike. Real <a href>
 * links, not onClick-only buttons -- middle-click/cmd-click to open a screen in a new
 * tab, right-click to copy its link, and a screen reader announces these as links to
 * somewhere, all for free, none of it reachable from a bare button.
 */
export function Nav({ activeId, onNavigate }: { activeId: string | undefined; onNavigate: (hash: string) => void }) {
  return (
    <nav className="nav" aria-label="Screens">
      <a
        href=""
        className="nav-wordmark"
        onClick={(e) => {
          e.preventDefault();
          onNavigate("");
        }}
      >
        Recoup
      </a>
      <div className="nav-items">
        {SCREENS.map((s) => (
          <a
            key={s.id}
            href={s.hash}
            className={`nav-item${activeId === s.id ? " nav-item-active" : ""}`}
            aria-current={activeId === s.id ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              onNavigate(s.hash);
            }}
          >
            {s.navLabel}
          </a>
        ))}
      </div>
    </nav>
  );
}
