import type { Metadata } from "next";
import { ConfirmTeamFlow } from "./confirm-team-flow";

export const metadata: Metadata = {
  title: "Confirm your team — GafferTalk",
  description: "Load and confirm your current Fantasy Premier League squad.",
  robots: { index: false, follow: false },
};

export default function TeamPage() {
  return <ConfirmTeamFlow />;
}
