import { useRoute } from "./app/routes";
import WorkspacePage from "./pages/workspace/WorkspacePage";
import IntakePage from "./pages/intake/IntakePage";
import ReviewPage from "./pages/review/ReviewPage";
import "./app/shell.css";
import "./shared/primitives.css";
import "./app/viewport.css";

export default function App() {
  const route = useRoute();
  return (
    <>
      <WorkspacePage route={route} />
      {route === "sources" && <IntakePage />}
      {route === "review" && <ReviewPage />}
    </>
  );
}
