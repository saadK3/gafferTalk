import type { Metadata } from "next";
import { RecommendationExperience } from "./recommendation-experience";

export const metadata: Metadata = {
  title: "Make the call — GafferTalk",
  description: "Ask about your FPL squad and compare legal transfer options.",
  robots: { index: false, follow: false },
};

export default function RecommendPage() {
  return <RecommendationExperience />;
}
