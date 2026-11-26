/**
 * Feature flags for work that ships in code but stays off the public site until it's
 * signed off. Pure constants: no env, React or DOM, so web and Expo read the same values.
 */
export const FEATURES = {
  /**
   * NCAA player W.Add (to date) column on the Impact tab. On since the 2026-11-26 calibration
   * (market-value chain slopes 1.0/1.0: team W.Add sums track schedule-neutral expected wins
   * with closure slopes 0.96 offense / 0.93 defense).
   */
  ncaaPlayerWinsAdded: true,
} as const;
