# Controlled small sample

This fixture is generated deterministically by:

```powershell
python tests/fixtures/build_controlled_sample.py .work/controlled-small-sample
```

It contains exactly 128 synthetic files. No historical thesis, real face image,
credential, questionnaire response, interview, database, or private source file
is included. Executable-looking files contain inert text markers only.

Use the generated directory as `source_mount.root_uri`, copy
`ingest-config.example.json` beside it, and replace the example file URI.
