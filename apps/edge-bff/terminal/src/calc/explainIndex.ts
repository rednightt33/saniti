/* EXEC-IND-CARDS: every explainer, by Flow id and by technical registry key (the card and the tests read these) */
import type { FlowExplainer, TechExplainer } from './explain';
import { FLOW_EXPLAIN_A } from './explainFlowA';
import { FLOW_EXPLAIN_B } from './explainFlowB';
import { TECH_EXPLAIN_A } from './explainTechA';
import { TECH_EXPLAIN_B } from './explainTechB';

export const FLOW_EXPLAIN: Record<string, FlowExplainer> = { ...FLOW_EXPLAIN_A, ...FLOW_EXPLAIN_B };
export const TECH_EXPLAIN: Record<string, TechExplainer> = { ...TECH_EXPLAIN_A, ...TECH_EXPLAIN_B };
