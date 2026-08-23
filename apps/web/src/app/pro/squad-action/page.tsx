import type { Metadata } from "next";
import { ProSquadActionExperience } from "./squad-action-experience";

export const metadata: Metadata = {
  title: "Best squad action | GafferTalk Pro",
  description: "Compare the best legal FPL squad action with rolling and taking a hit.",
};

export default function ProSquadActionPage() {
  return <ProSquadActionExperience />;
}
