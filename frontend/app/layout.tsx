import type { Metadata } from "next";
import { Bricolage_Grotesque, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { Rail } from "@/components/shell/Rail";
import { ModeBanner } from "@/components/shell/ModeBanner";

const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
  axes: ["wdth", "opsz"],
});
const plex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex",
});

export const metadata: Metadata = {
  title: "Oracle",
  description: "Simulate a world of people to see how your product, idea or decision will land.",
};

const themeScript = `try{var t=localStorage.getItem('oracle-theme');if(t)document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${bricolage.variable} ${plex.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-dvh">
        <div className="flex min-h-dvh">
          <Rail />
          <main className="min-w-0 flex-1 pb-20 md:pb-0">
            <ModeBanner />
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
