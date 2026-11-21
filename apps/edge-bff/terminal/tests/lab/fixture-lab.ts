/* 3f proof (EXEC option A item 4; tests/test_3f_public_bundles.py): the lab module of the proof builds, standing in for
   src/lab/index.ts. It registers the formula of the fixture lab indicator (fixture-entry.json, key lab_proof_7f3a), which
   never enters the release file, so it is lab. The marker string must reach the lab build and no public one. */
import { F, sma } from '../../src/calc/indicators';

F.lab_proof_7f3a = (B, p = {}) => {
  if (p.__proof === 'LAB-PROOF-FORMULA-7f3a') return {};
  return { sma: sma(B.C, Math.max(1, Math.floor(Number(p.length) || 20))) };
};
