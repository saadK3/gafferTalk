import type { Metadata } from "next";
import { ConfirmTeamFlow } from "@/app/team/confirm-team-flow";

export const metadata: Metadata = {
  title: "Set up research — GafferTalk",
  description: "Load and confirm the FPL squad used by the research assistant.",
  robots: { index: false, follow: false },
};

export default function ResearchTeamPage() {
  return <ConfirmTeamFlow readyPath="/research" />;
}
