# Committed field intelligence

Claims in this directory ship with the app. They work with no database attached,
they are read only at runtime, and a reviewer can read the diff in git, which is
why anything the team wants to keep permanently belongs here rather than only in
Postgres.

Everything the team adds through the **Teach** page goes to Postgres. To promote
that into a committed claim, take the snapshot from `/api/intel/export` and save
it as a `.json` file here.

## Shape

Any `*.json` file in this directory, holding either a bare list or an object with
an `intel` key:

```json
{
  "intel": [
    {
      "competitor": "o9 Solutions",
      "ia_product": "AttributeSmart",
      "kind": "gap",
      "claim": "Attribute tagging is delivered as a services engagement rather than a product.",
      "detail": "Their solution engineer said so in the August bake off, when asked who maintains the taxonomy.",
      "confidence": "field",
      "source": "",
      "author": "Competitive Marketing",
      "as_of": "2026-08-14"
    }
  ]
}
```

`kind` is one of the keys in `intel.KINDS`. `confidence` is one of `verified`,
`field` or `hearsay`, and each tier carries its own rule about what a card may do
with the claim, defined in `intel.CONFIDENCE`. A `verified` claim must carry a
source. A claim that fails validation is skipped with a warning in the log rather
than shipped half-formed.
