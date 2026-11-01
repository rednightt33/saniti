/* EXEC-IND-CARDS IC4: technical explainers (calc/explain.ts: the interface, the helpers and the rule that the card's
   number is the chart's number). One file per part so they can be written side by side; explainTechIndex.ts joins them. */
import type { TechExplainer } from './explain';
import { dateOf, fmt, intOf, sourceAt, SOURCES } from './explain';

/* I27-I53 (see explainTechA.ts for the reference) */
export const TECH_EXPLAIN_B: Record<string, TechExplainer> = {
};
