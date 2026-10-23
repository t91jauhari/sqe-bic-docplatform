import type { Metadata } from "next";
import "./globals.css";
import "./corporate.css";
import { PlatformProvider } from "@/components/platform-provider";

export const metadata: Metadata = {
  title: "SQE · Document Automation",
  description: "Document intelligence and SOP review cockpit",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <PlatformProvider>{children}</PlatformProvider>
      </body>
    </html>
  );
}
