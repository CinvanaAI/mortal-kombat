# Future ideas

The tournament was also an excuse to make model evaluation fun. These are ideas to explore, not features included in the current application or promised releases.

## Pick your fighters

An original character-selection screen could turn the model inventory into a roster. Each model would have a character, its actual model ID, connection status, documented limits and available rate information. Select contestants and a judge, choose the task and rubric, and enter the arena.

The characters would be our own designs. Their appearance would express personality, not imply that a larger character is a better model or that a vendor endorses the project. The underlying model identity and evidence would always be accessible.

## Watch the evidence become a match

The idea was to watch an animated fight as results arrived: a judged win becomes an attack, the opponent reacts, and the final decision triggers an original finishing move. The plain-language reason and actual answers would remain one click away.

A possible sequence:

1. **The challenge:** show the task, test examples and rubric before the match starts.
2. **The responses:** show both contestants working and their actual outputs arriving. Waiting is waiting; a progress animation would not pretend to measure model reasoning.
3. **The exchange:** translate a recorded comparison into a move using a visible, consistent rule.
4. **The verdict:** show the judge's reason alongside the winner's final flourish.
5. **The replay:** pause the match and open the original input, responses and judgment behind an event.

There is a design problem to solve before building this: today's Battle judges the **whole example set once**. The historical ten-example battles also contain one whole-set verdict, not ten individual round scores. A replay of those records must show one judged outcome. Per-example combat rounds would require new, explicitly recorded per-example judgments. Health bars, damage values and animations would be presentation rules, never invented rubric scores or statistical confidence.

Failures need their own treatment too: a connection error is an interrupted bout; disqualification is a judge or validation outcome. Neither should masquerade as an ordinary losing answer. A reduced-motion or static replay would retain the complete explanation.

## Make the experiments more informative

These are engineering possibilities for a later iteration:

| Idea | Why explore it? | What would need to be decided? |
| --- | --- | --- |
| Repeat a battle with different judges and swapped A/B positions | See how much a result depends on the judge and presentation order | Repetition budget, aggregation and how disagreements remain visible |
| Compare different tournament seed orders or use a full round robin | Examine how the insertion ladder affects the final order | Additional calls, ties and non-transitive preferences |
| Plot quality alongside available cost evidence | Help choose models for a particular task and spending preference | Which quality measure is justified, and how missing prices/usage are shown |
| Resume a saved experiment | Avoid repeating completed calls after an interruption | Exact task/model version matching, stale data and explicit reuse rules |
| Research model documentation from selected sources | Reduce manual preparation | Source retrieval, identity matching, freshness and review before applying limits |
| Export evaluation datasets to other tools | Carry the experiment into a broader evaluation workflow | Preserve task, judge and provenance; never invent missing numeric scores |

## Recover more of the original ideas

There are more historical conversations and experiments to revisit. Future recovery should add specific, reviewed context when it explains a design decision or supplies useful evidence. Private conversations and raw archives are not part of this repository.

For what actually works today, read [Project status](STATUS.md). For larger tools covering related ground, read [Related tools](RELATED-TOOLS.md).
