// ISO3 -> ISO 3166-1 numeric (world-atlas feature ids) and label anchors [lon, lat].
export const ISO_NUM: Record<string, string> = {
  USA: "840", CAN: "124", MEX: "484", BRA: "076", ARG: "032", CHL: "152", COL: "170", GBR: "826", IRL: "372",
  DEU: "276", FRA: "250", NLD: "528", ESP: "724", ITA: "380", SWE: "752", POL: "616", CHE: "756", NOR: "578",
  IND: "356", PAK: "586", BGD: "050", CHN: "156", JPN: "392", KOR: "410", SGP: "702", IDN: "360", VNM: "704",
  PHL: "608", MYS: "458", AUS: "036", ARE: "784", SAU: "682", ISR: "376", TUR: "792", ZAF: "710", NGA: "566",
  KEN: "404", EGY: "818", RUS: "643",
};

// Where to anchor arcs and where to scatter agents when a country is too small to draw.
export const ANCHOR: Record<string, [number, number]> = {
  USA: [-98, 39], CAN: [-104, 57], MEX: [-102, 23.5], BRA: [-51, -10], ARG: [-64, -35], CHL: [-71, -33], COL: [-73.5, 4],
  GBR: [-2, 53.5], IRL: [-8, 53.2], DEU: [10.4, 51], FRA: [2.4, 46.6], NLD: [5.4, 52.2], ESP: [-3.6, 40.2], ITA: [12.6, 42.8],
  SWE: [16, 62], POL: [19.3, 52], CHE: [8.2, 46.8], NOR: [9, 61], IND: [79, 22], PAK: [69.5, 30], BGD: [90.3, 23.8],
  CHN: [103, 34.5], JPN: [138.5, 36.5], KOR: [127.8, 36.4], SGP: [103.82, 1.35], IDN: [113, -1.5], VNM: [106, 15.8],
  PHL: [122, 12.5], MYS: [102, 3.9], AUS: [134, -25], ARE: [54.2, 24], SAU: [45, 24], ISR: [35, 31.4], TUR: [35, 39],
  ZAF: [24.5, -29], NGA: [8, 9.6], KEN: [37.9, 0.4], EGY: [30, 26.8], RUS: [95, 61],
  // Blocs
  EU: [9.5, 49.5], GCC: [49, 24.5], ASEAN: [108, 8], BRICS: [60, 20], global: [0, 20],
};

/** Small deterministic PRNG so the same agent always lands on the same spot. */
export function seeded(id: string) {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return () => {
    h += 0x6d2b79f5;
    let t = h;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
