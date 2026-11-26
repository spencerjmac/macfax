/**
 * Feature flags for work that ships in code but stays off the public site until it's
 * signed off. Pure constants: no env, React or DOM, so web and Expo read the same values.
 */
export const FEATURES = {
  /**
   * NCAA player W.Add (to date) column on the Impact tab. The API field (wins_added) and
   * the pipeline step (compute_market_values in update_ncaa_players) stay on; only the
   * column is hidden while the NCAA win calibration is reviewed (2026-11-25).
   */
  ncaaPlayerWinsAdded: false,
} as const;
