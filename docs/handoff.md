# Handoff

The bots hand work to each other through the Telegram group, with files as
attachments. The three bots do not share a checkout and do not push. Only the
publisher daemon commits, to branch `data`.

The full protocol (message headers, who wakes on what, which files travel with which
message, when to stay silent, how to send, and the Hermes settings every bot needs)
is the shared skill [skills/sanity-protocol/SKILL.md](../skills/sanity-protocol/SKILL.md),
loaded by all three bots.

In short:

```
person   --paper-------------------------------------------------> Reader
Reader   --sanity run=<slug> to=verifier stage=verifier + equations.json --> Verifier
Verifier --sanity run=<slug> status=started ... + PLAN.md -----------> group
Verifier --sanity run=<slug> to=reader question=<q> (optional) ------> Reader
Reader   --sanity run=<slug> to=verifier answer=<q> -----------------> Verifier
Verifier --sanity run=<slug> to=writer stage=writer + equations.json, verdicts.json, bundle --> Writer
Writer   --sanity run=<slug> status=done + REPORT.md ----------------> group
Writer   --sanity run=<slug> to=publisher stage=publish + one zip --> Publisher
Publisher --publish_run.py, commit message site, push data ---------> site
```

The LLM bots never hold GitHub credentials. A `to=publisher` message gets `NO_REPLY` from them.

`runs/example-oscillator/` in this repo is a worked example used by the tests, not a
handoff location.
