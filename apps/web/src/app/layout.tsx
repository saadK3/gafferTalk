import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://gaffertalk.com"),
  title: "GafferTalk — Make the call",
  description:
    "Clear, legal Fantasy Premier League transfer options grounded in your squad.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "GafferTalk — Your team. Your call.",
    description:
      "GafferTalk does the homework—checking the data, budget and FPL rules before laying out your options.",
    url: "/",
    siteName: "GafferTalk",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "GafferTalk transfer check" }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "GafferTalk — Your team. Your call.",
    description: "GafferTalk does the homework. You make the call.",
    images: ["/og.png"],
  },
  robots: { index: true, follow: true },
};

type RootLayoutProps = Readonly<{ children: ReactNode }>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
