import type { Metadata } from "next";
import { ProRouteExperience } from "./pro-route-experience";

export const metadata: Metadata = {
  title: "Route finder | GafferTalk Pro",
  description: "Find and validate bounded one- and two-transfer routes to an FPL target.",
};

export default function ProRoutesPage() {
  return <ProRouteExperience />;
}
