# EStG § 32(4): source-bound repair worklist

The third native generation failed without a signature. A fourth generation is
not ready: fixing its leap-day expression would still leave the substantive
eligibility routes unimplemented. The prior request restricted local inputs to
two birth-register fields while requiring the complete source unit. Those fields
cannot determine employment, education, service or disability eligibility.
Repeating that restriction cannot produce a complete module.

The review evidence is committed in
[`adult-child-repair-review.json`](../conformance/closure/de-discovery-2026-09-08/adult-child-repair-review.json).
It contains the complete pinned § 32(4) text, twelve fully read, hash-verified
DA-KG sections (including the structural A 20.2 heading) and the complete BFH
III R 37/21 and III R 10/22 decisions. The remaining guidance families listed below still need their
own implementation review; listing them does not declare them reviewed or encoded.

## Source-unit coverage

The parser exposes the paragraph and sentence owners `(4)`, `(4)(satz-1)`,
`(4)(satz-2)` and `(4)(satz-3)`. Numbered and lettered routes below describe
content within those owners. They are not additional corpus citation paths.

| Route | Observable records to investigate | Computation that must remain a rule | Open source work |
| --- | --- | --- | --- |
| Sentence 1, introductory age condition | Live-birth register entry and date | Attainment of 18 and overlap with the actual qualifying interval | Reuse signed § 32(3) BGB § 187/188 date expression and literal proofs |
| Sentence 1, number 1 | Agency/Jobcenter certificates, registration events, employment contracts and amendments | Under 21; qualifying registration; employment exclusion and its exceptions | A 14.1–14.2; SGB III § 38(4), SGB IV §§ 8/8a and SGB II § 16d; foreign registration scope |
| Sentence 1, number 2(a) | Course enrolments, attendance, examination/result notices, training contracts and interruption records | Qualifying vocational training and its start/end/interruption intervals | A 15.1–15.11; registration alone cannot establish every training route |
| Sentence 1, number 2(b) | Actual preceding and following training/service events, applications and admission records | Qualifying endpoints and a transition of no more than four full calendar months | A 16 plus the actual endpoint definitions; no generic caller-supplied gap length |
| Sentence 1, number 2(c) | Applications, rejections, offers, agency certificates, medical records where relevant | Inability to start/continue specifically because no training place is available | A 17.1–17.2; a pending application alone is insufficient |
| Sentence 1, number 2(d), aa and bb | Issued service agreements, placement/provider records, service dates | Social/ecological year definitions | JFDG and A 18.2 |
| Sentence 1, number 2(d), cc | Issued service agreement and service dates | Federal voluntary service definition | BFDG and A 18.3 |
| Sentence 1, number 2(d), dd | Programme award/agreement and activity dates | European Solidarity Corps activity and programme scope | Regulation (EU) 2021/888 and A 18.4 |
| Sentence 1, number 2(d), ee | Overseas service agreement and provider recognition records | Other service abroad definition | BFDG § 5 and A 18.5 |
| Sentence 1, number 2(d), ff | Grant/service agreement and provider records | Qualifying weltwärts service | Referenced 2016 funding guideline and A 18.6 |
| Sentence 1, number 2(d), gg | Service agreement, engagement dates and time records | All-generations service definition | SGB VII § 2(1a) and A 18.7 |
| Sentence 1, number 2(d), hh | Service agreement and recognition records | International youth voluntary service definition | Referenced 2021 guideline and A 18.8 |
| Sentence 1, number 3 | Medical reports and issued decisions with onset/evidence dates; actual income receipts, tax and insurance payments; need-related records | Disability definition, onset limit and applicable transition, causation, necessary need and disposable resources | A 19.1–19.6; SGB IX; EStG § 52 transition and all quantified income/need prerequisites |
| Sentence 2 | Qualifications, examination results, course sequence and employment records | First qualification/degree, multi-stage training and restriction limited to number 2 | A 20.1–20.2.4; a caller-supplied first-training-completed flag is insufficient |
| Sentence 3 | Contracts/amendments, schedules, employment and training records | Aggregate regular hours, temporary expansion, training employment and marginal employment | A 20.3–20.3.3; complete SGB IV §§ 8/8a, beyond the signed amount threshold |
| Monthly projection | The derived daily/interval results of all applicable conditions | Existence of at least one day satisfying the conditions together | A 20.4 and § 66(2); separate monthly overlaps do not establish simultaneous satisfaction |

The records column proposes evidence boundaries for implementation review. It
does not authorize replacing any named computation with a Boolean input or
assert that those records suffice for every legal case.

## Findings that change the repair request

* **Registration is not a simple open/close interval.** A 14.1 expressly says
  deletion of registration alone does not terminate the job-seeker condition.
  BFH III R 37/21 paragraphs 17–21 also distinguish an effectively notified
  termination decision and the child’s own termination request from mere register
  deletion or ending a careers-advice appointment. Without those acts, a
  source-defined breach authorizing termination matters; breach is not the only
  termination route. Disputed termination requires version-bound SGB III § 38
  analysis. The existing A 14.1 disposition is corrected accordingly. It also permits
  specified marginal work, self-employment below 15 hours and EU/EEA/Swiss
  employment-agency registration. A domestic-registration Boolean and a blanket
  no-work Boolean would miss these routes.
* **Transition months are calendar months.** A 16 gives July end/December start
  as a qualifying four-full-month transition. Its clock begins at the prior
  endpoint even before age 18. The next endpoint must itself qualify; a bare
  difference between two supplied dates cannot decide the route.
* **Disability evidence has a bearing period rule.** A 19.2(2) sentence 1 limits
  consideration to the proven period. Sentence 2 says expiry of a time-limited
  SGB IX card does not itself limit the award. The former whole-section
  `evidence_and_review` exclusion is corrected to an open bearing disposition.
* **Age 25 is not universal for historical disability onset.** A 19.1(4)
  explicitly identifies the § 52 transition for disability arising before
  1 January 2007 between ages 25 and 27. The present paragraph's age-25 rule
  cannot be represented as exhaustive without that dependency.
* **The 20-hour test is a computation over records.** A 20.3.1 requires the
  contractual hours, monthly-hours conversion by 4.35, relevant periods after
  first qualification, aggregation and the limited two-month expansion test.
  Full calendar weeks and the qualifying period within a calendar year matter;
  a year boundary does not restart an expansion. Training-employment hours are
  excluded from the stated aggregation. A single regular-hours input hides law.
* **Monthly conjunction must be contemporaneous.** A 20.4 requires the
  conditions on at least one day together. Age-window overlap and a separate
  monthly training/work flag can produce false positives when their intervals
  do not intersect.

* **The two training definitions differ.** A 20.2.1 defines the completed
  qualification that triggers sentence 2 more narrowly than the training ground
  in sentence 1 number 2(a). A school certificate, voluntary internship or
  traineeship is not automatically a first completed vocational qualification.
  Regulated qualifications, equivalent expertise examinations and foreign
  qualifications require their stated source conditions. A 20.2.2 treats later
  formal training after work without a qualification as first training;
  recognition adjustment measures belong to the preceding foreign qualification.
  A 20.2.3 requires the stated higher-education recognition and equivalence;
  changing or interrupting an unfinished degree does not complete it.
* **A voluntary-service interval does not restart the multi-stage training
  clock.** A 20.2.4(2) and BFH III R 10/22 paragraphs 19–32 require the connection
  between the actual training stages and the earliest available next start.
  Choosing an intervening FSJ despite an available start does not preserve that
  connection merely because the next degree starts promptly after service.
  The service and four-calendar-month transition consideration grounds do not
  replace this separate sentence-2 assessment. The decision leaves room for a
  specifically established vocational-training exception; do not turn its
  ordinary FSJ treatment into an exceptionless service exclusion.
* **Multi-stage training requires more than dates or a Boolean.** A 20.2.4
  requires objective evidence of the further goal arising before the next stage;
  late disclosure to the Familienkasse is harmless. Subject and timing connection,
  objectively unavailable places and the role of intervening work matter. Work
  required only for admission to the final examination differs from work required
  before the next stage can begin. The four indicators in paragraph 3, including
  a commitment exceeding 26 weeks, inform an overall assessment of all the
  circumstances. They are not an automatic OR rule or a numeric score. The
  implementation of that assessment remains unresolved; neither an invented
  score nor a caller-supplied `first_training_completed` judgment is acceptable.
* **Completion dates and degree sequences have exceptions.** A 20.2.4(5)–(11)
  distinguishes passing a vocational examination from the ordinary university
  result-notification date, with intervening full-time work in the intended
  profession relevant. Intermediate examinations do not complete a degree.
  Consecutive masters, parallel courses, postgraduate courses, legal/teaching
  preparatory service and doctoral preparation retain the stated temporal,
  substantive and predominant-employment qualifications. Section 9(6)'s separate
  first-training criteria must not be imported into this test.

## Required behavioral witnesses

These are planned acceptance cases, not claims of executed tests:

1. Ordinary and leap-day births, including 28 February versus 1 March, using
   the supported two-argument date function and signed correction expression.
2. Conditions occurring in disjoint parts of one month versus one common day;
   the former must not qualify merely because each overlaps the month.
3. Registration deletion or ending a careers-advice appointment alone versus an
   effectively notified termination decision, the child’s own termination request,
   and the source-defined breach route; bind the applicable SGB III version.
4. Qualifying July/December training endpoints versus a January next endpoint;
   include a prior endpoint before the eighteenth birthday.
5. Disability evidence ending mid-month versus card expiry alone, and evidence
   wholly outside the queried month.
6. Disability before 2007 between ages 25 and 27 versus otherwise identical
   onset outside the transition; no current-age cutoff for the disability route.
7. Monthly contractual hours converted by 4.35, concurrent employments around
   20 hours, and training-employment hours excluded as the source prescribes.
8. Temporary expansion of two months versus more than two, including a year
   boundary and averages on each side of 20 hours.
9. Harmful work starting during a month versus covering the entire month,
   while also checking that the underlying number-2 condition actually exists.
10. First qualification completed versus not completed, with otherwise identical
    number-1 and disability cases demonstrating that sentence 2 does not apply
    to those routes.
11. A vocationally relevant internship followed by work exceeding 20 hours versus
    an actually completed first vocational qualification; apply the distinct
    sentence-1 and sentence-2 definitions before testing harmful work.
12. Bachelor-to-master continuation at the first available start versus a
    personal choice of intervening FSJ despite an available start; do not measure
    the multi-stage connection from the service end date.
13. Objective evidence created before the next training stage but disclosed late
    versus evidence created only afterwards. Include an objectively unavailable
    place and work required solely for the final examination.
14. Employment indicators straddling 26 weeks with different overall
    circumstances; no single indicator supplies an automatic decision.
15. Passing an examination, receiving its result, and starting full-time work in
    the intended profession on different dates; include an intermediate exam and
    an unfinished degree change.

Every omitted external prerequisite must identify the actual source reference
and missing absolute output. Local computations cannot be deferred as runtime
gaps when the runtime supports their operations. No generated module, manifest,
test expectation or signing gate is edited as part of this review.
