import type { Metadata } from "next";
import { RecommendationExperience } from "./recommendation-experience";

export const metadata: Metadata = {
  title: "Free Quick Actions — GafferTalk",
  description: "Compare legal FPL transfer options using three deterministic Quick Actions.",
  robots: { index: false, follow: false },
};

export default function RecommendPage() {
  return <RecommendationExperience />;
}
