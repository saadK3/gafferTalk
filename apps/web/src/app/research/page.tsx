import type { Metadata } from "next";
import { ResearchExperience } from "./research-experience";

export const metadata: Metadata = {
  title: "Research assistant — GafferTalk",
  description: "Ask facts-first Fantasy Premier League questions about your confirmed team.",
  robots: { index: false, follow: false },
};

export default function ResearchPage() {
  return <ResearchExperience />;
}
