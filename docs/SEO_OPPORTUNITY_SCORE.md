# SEO Opportunity Score v1

A prioritisation heuristic. **Not a prediction**, and the output says so.

## Components and weights

| Component | Weight | Source |
|---|---|---|
| commercial intent | 0.25 | classified intent |
| business relevance | 0.20 | mean relevance of retrieved sources |
| conversion potential | 0.15 | does the vertical have a CTA for this intent |
| content gap | 0.15 | page shapes the SERP is not serving |
| SERP opportunity | 0.10 | domain fragmentation minus feature crowding |
| search demand | 0.10 | keyword volume, if a provider supplied it |
| competition | 0.05 | competition index, inverted |

The weighting deliberately favours intent and business fit over volume, which is
the mission's stated position: a keyword with 300 highly qualified searches should
outrank an informational one with 10,000. `test_low_volume_high_intent_can_beat_high_volume_low_intent`
pins that behaviour.

## The three rules that keep it honest

**1. Unknown never becomes zero.** A missing input is dropped from the weighted
average and named in `missing_inputs`. Scoring it zero would drag the total down
and read as evidence of a poor opportunity, when the truth is that nobody measured
it.

**2. Components are stored separately.** An operator who disagrees can see which
part they disagree with, and each carries a `rationale` string.

**3. `confidence` is the share of weight actually measured.** A score of 78 with
confidence 0.45 reads as "promising, poorly evidenced". Without a SERP provider or
keyword metrics, confidence sits near 0.6 and everything volume-related is UNKNOWN.

## Output

```json
{
  "overall_score": 74,
  "confidence": 0.65,
  "version": "v1",
  "components": [{"code": "...", "value": 85.0, "weight": 0.25,
                  "known": true, "rationale": "..."}],
  "missing_inputs": ["search_demand", "competition"],
  "known_component_count": 5,
  "total_component_count": 7,
  "interpretation": "Prioritisation heuristic, not a prediction. ..."
}
```

`overall_score` is `null` when nothing at all could be measured — not 0.

## Search demand curve

Log-shaped, so volume informs without dominating: 10 → ~20, 100 → ~40,
1 000 → ~60, 10 000 → ~80.

## What this is not

It is not calibrated against outcomes. Phase 7 is meant to replace these weights
with ones learned from real Prospect 360 conversion data. Until a lead has been
attributed to a page, every weight here is an informed guess, and the version field
exists so a later model can be told apart from this one.
