# Open research questions

## 1. What is the right unit of an interrogation?

Should the knowledge base store raw programs, relation instances, command histories, or symbolic candidate partitions as primary nodes? A hypergraph over relation families is expressive but may be expensive. A promising experiment is to compare AST-centric and consequence-centric KBs.

## 2. Can relation discovery itself be synthesized?

Version 1 starts with trusted relation templates. A harder problem is to synthesize transformations plus relational invariants, then discharge them with relational symbolic execution. The search space could include paired program sketches and a grammar of observation normalizers.

## 3. How can proof strength influence query selection?

A query with a theorem-level certificate may be less informative than one with a bounded certificate. Selection could treat proof risk as a cost or maintain separate trusted/untrusted frontiers. This resembles proof-carrying testing.

## 4. Can the fault model be inferred jointly with the secret?

Instead of fixing the guard and replay transition, introduce model holes:

- bank projection/S-box family;
- phase guard;
- signed replay behavior;
- state update;
- quantization/noise bounds.

Interrogation trick queries then distinguish fault models as well as secrets. This connects observation refinement with CEGIS.

## 5. How should secret and state uncertainty be factored?

A full joint formula is exact but large. Alternatives:

- alternating inference;
- factor graphs or message passing;
- learned state abstraction with retractable assumptions;
- lane-local secret marginals plus a global permutation solver;
- belief-state automata.

The synthetic ground truth allows direct comparison of approximation errors.

## 6. What is a sound notion of information gain with solver samples?

Diverse SMT models are not uniform samples. Committee disagreement is useful but not a calibrated entropy estimate. Research options include hashing-based approximate counting/sampling, weighted model integration for noise, or worst-case partition objectives that avoid priors.

## 7. Can synthesis optimize statistical power directly?

Instead of scoring predicted cycle margins heuristically, synthesize query families to minimize expected SPRT sample count under candidate outcome distributions. This requires a credible noise model and may produce different repetition/context choices.

## 8. Can a reducer preserve semantic information exactly?

Constraint equivalence under the current hypothesis is an SMT-checkable reduction predicate. Does preserving equivalence yield much larger witnesses than preserving a core implication? Can grammar-integrated shrinking outperform external delta debugging for relation families?

## 9. How should interrogation diversity be measured?

Structural diversity may not correspond to semantic diversity. Candidate partition signatures, unsat-core provenance, learned-state transitions, and relation-composition paths offer alternatives. A submodular coverage objective may provide a principled selection rule.

## 10. Can active learning discover the best macro alphabet?

A manually fixed alphabet can hide distinctions or explode in size. One could synthesize parameterized macro symbols whose concrete instances maximize state-hypothesis disagreement, approaching active learning for register automata.

## 11. Are there phase transitions in fault learnability?

By varying bucket width, noise, guard probability, state persistence, and query cost, measure where recovery changes from trivial to feasible to impossible for a fixed grammar/budget. Compare empirical thresholds with information-theoretic lower bounds.

## 12. Can an adaptive strategy be compiled?

After solver-guided campaigns, synthesize a compact decision tree or finite-state controller that recovers secrets without online SMT. Verify it over the complete tutorial domain and compare worst-case query complexity.

## 13. What counterexample best refines query synthesis?

A failed candidate can receive:

- one unseparated model pair;
- the largest partition;
- an adversarial noise/state witness;
- an unsat core explaining why no margin exists.

Which counterexample form yields fastest CEGIS convergence?

## 14. Can interrogation expose unsound analyzers inside Interrogator?

The symbolic extractor, state learner, and statistics are themselves analyzers. Metamorphic/interrogation tests can be applied recursively: generate concrete small models and force their predictions into contradiction. This makes the project a self-testing program-analysis laboratory.

## 15. What should impossibility look like?

Some hidden configurations may be observationally equivalent under the grammar and budgets. The system should be able to produce an indistinguishability certificate or bounded evidence, not merely time out. Synthesis can search for a discriminator; unsatisfiability over a complete finite grammar gives a bounded impossibility result.
