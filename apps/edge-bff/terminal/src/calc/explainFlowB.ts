/* EXEC-IND-CARDS IC3: Flow explainers (calc/explain.ts: the interface, the helpers and the rule that the card's number
   is the chart's number). One file per part so they can be written side by side; explainFlowIndex.ts joins them. */
import type { BrokerSums, FlowExplainer } from './explain';
import { againstLevels, brokerRow, filterOf, filterText, flowWindow, fmt, intOf, levelsOf, spanOf, topBy, windowSums } from './explain';

/* FL20-FL39 except FL24 (see explainFlowA.ts for the reference) */
export const FLOW_EXPLAIN_B: Record<string, FlowExplainer> = {
};
