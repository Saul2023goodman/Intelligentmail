import { useRoute } from "./app/routes";
import WorkspacePage from "./pages/workspace/WorkspacePage";
import IntakePage from "./pages/intake/IntakePage";
import ReviewPage from "./pages/review/ReviewPage";
import ExecutionPage from "./pages/execution/ExecutionPage";
import MailboxPage from "./pages/mailbox/MailboxPage";
import RecordsPage from "./pages/records/RecordsPage";
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
      {route === "execution" && <ExecutionPage />}
      {route === "mailbox" && <MailboxPage />}
      {route === "records" && <RecordsPage />}
    </>
  );
}
