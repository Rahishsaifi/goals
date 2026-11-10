# Scoring methodology

Weighted score:

`weighted_contribution = criterion_weight * criterion_score / 100`

`overall_score = sum(weighted_contribution for applicable weighted criteria)`

Rules:

- Weights are non-negative and must sum to exactly 100.
- Mandatory status is separate from the weighted score.
- Mandatory outcomes are `satisfied`, `not_satisfied`, or `unknown`.
- Missing evidence is `unknown`, not proof the candidate lacks the qualification.
- LLMs assess evidence; Python calculates the fit score.
- Recruiter overrides are not yet implemented as a stored workflow.
- The score is decision support, not a probability of job success.
