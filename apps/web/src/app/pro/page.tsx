import type { Metadata } from "next";
import { ProResearchExperience } from "./pro-research-experience";

export const metadata: Metadata = {
  title: "Named Transfer Research — GafferTalk Pro",
  description: "Compare buying, holding, waiting and legal alternatives for an FPL transfer.",
  robots: { index: false, follow: false },
};

export default function ProPage() {
  return <ProResearchExperience />;
}
