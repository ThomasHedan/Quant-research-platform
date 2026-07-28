/**
 * Seuils de significativité statistique partagés par les sections de la
 * fiche stratégie. La couleur signal (`bg-signal`) est réservée STRICTEMENT
 * à ces cas — jamais à « rentable » (CLAUDE.md §4, contraintes de fond).
 * Seuils volontairement conservateurs, cohérents avec les exemples cités
 * dans la spec : |t| élevé, p-value basse, DSR élevé, PBO bas.
 */

/** |t| ≥ 2 ≈ p < 0,05 à deux queues pour un échantillon suffisamment grand. */
export function isSignificantTStat(tStat: number): boolean {
  return Math.abs(tStat) >= 2
}

export function isSignificantPValue(pValue: number): boolean {
  return pValue < 0.05
}

/** Un DSR proche de 1 signale un Sharpe qui survit à la déflation par le nombre d'essais. */
export function isRobustDsr(deflatedSharpeRatio: number): boolean {
  return deflatedSharpeRatio >= 0.95
}

/** Une probabilité de surapprentissage basse est le signal recherché — jamais l'inverse. */
export function isLowPbo(probabilityOfOverfitting: number): boolean {
  return probabilityOfOverfitting <= 0.1
}

/**
 * Une probabilité de breach (I5) matérielle mérite le rouge — pas la couleur
 * signal, réservée à la significativité statistique. Seuil conservateur :
 * en dessous, un chiffre non nul reste un artefact Monte Carlo attendu.
 */
export function isMaterialBreachRisk(probability: number): boolean {
  return probability >= 0.05
}
