import { useCallback, useEffect, useState } from "react";
import { AblationTableScreen } from "./components/AblationTableScreen";
import { AssumptionSlidersScreen } from "./components/AssumptionSlidersScreen";
import { CaseAuditScreen } from "./components/CaseAuditScreen";
import { Landing } from "./components/Landing";
import { ModelLayerPanel } from "./components/ModelLayerPanel";
import { Nav } from "./components/Nav";
import { ThreeBoundDecompositionScreen } from "./components/ThreeBoundDecompositionScreen";
import { TourChrome } from "./components/TourChrome";
import { SCREENS, screenByHash } from "./lib/screens";

const TOUR_PREFIX = "#tour/";

function SCREEN_BODY(id: string) {
  switch (id) {
    case "case-audit":
      return <CaseAuditScreen />;
    case "ablation":
      return <AblationTableScreen />;
    case "sliders":
      return <AssumptionSlidersScreen />;
    case "decomposition":
      return <ThreeBoundDecompositionScreen />;
    case "model":
      return <ModelLayerPanel />;
    default:
      return null;
  }
}

/**
 * Real hash-based routing, not a router library -- this is a 6-screen demonstration
 * instrument, and window.location.hash + a hashchange listener gets every property
 * that actually matters here (deep-linkable URLs, working back/forward, a bookmarkable
 * tour step) without a new dependency. Three location shapes:
 *   ""            -> landing (the default route)
 *   "#<screen-id>" -> that screen, standalone (nav-driven browsing)
 *   "#tour/<n>"    -> the guided tour, on step n, with next/back chrome
 */
function useHashLocation(): string {
  const [hash, setHash] = useState(() => window.location.hash || "");
  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash || "");
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  return hash;
}

function App() {
  const hash = useHashLocation();

  const isTour = hash.startsWith(TOUR_PREFIX);
  const tourStep = isTour ? Number.parseInt(hash.slice(TOUR_PREFIX.length), 10) : -1;
  const tourValid = isTour && Number.isInteger(tourStep) && tourStep >= 0 && tourStep < SCREENS.length;

  const standaloneScreen = !isTour ? screenByHash(hash) : undefined;
  const activeScreen = tourValid ? SCREENS[tourStep] : standaloneScreen;

  const goTo = useCallback((next: string) => {
    window.location.hash = next;
  }, []);

  useEffect(() => {
    document.title = activeScreen ? `Recoup — ${activeScreen.navLabel}` : "Recoup — Revenue Recovery, Audited";
  }, [activeScreen]);

  // A malformed tour hash (#tour/9, #tour/abc) is a broken deep link, not a reason to
  // silently fall back to the landing page and hide that the link was wrong.
  if (isTour && !tourValid) {
    return (
      <>
        <Nav activeId={undefined} onNavigate={goTo} />
        <main className="screen">
          <h1>That tour step doesn't exist</h1>
          <p className="load-error-help">
            Valid steps are <code>#tour/0</code> through <code>#tour/{SCREENS.length - 1}</code>.
          </p>
          <button type="button" className="btn-primary" onClick={() => goTo(SCREENS[0].hash)}>
            Start the tour from the beginning
          </button>
        </main>
      </>
    );
  }

  if (!activeScreen) {
    return (
      <>
        <Nav activeId={undefined} onNavigate={goTo} />
        <Landing onNavigate={goTo} />
      </>
    );
  }

  return (
    <>
      <Nav activeId={activeScreen.id} onNavigate={goTo} />
      {SCREEN_BODY(activeScreen.id)}
      {isTour && (
        <TourChrome
          stepIndex={tourStep}
          onNavigate={goTo}
          onExit={() => goTo("")}
        />
      )}
    </>
  );
}

export default App;
