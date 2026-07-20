import type { Metadata } from "next";
import "./pivotglass.css";

export const metadata: Metadata = {
  title: "Pivotglass",
  description: "Local evidence-first adversary intelligence cockpit",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
