import "./App.css";
import { CaseAuditScreen } from "./components/CaseAuditScreen";

// Flat and obvious, per docs/day5surfaceplan.md: this is a demonstration instrument
// for one viewer, five minutes, not an app. One screen today (Stage 2); later stages
// add siblings here, not a router or a nav shell.
function App() {
  return <CaseAuditScreen />;
}

export default App;
