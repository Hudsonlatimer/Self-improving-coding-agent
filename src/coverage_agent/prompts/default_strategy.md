# Coverage checklist

- Read the uncovered function before writing a test.
- Assert the return value or the raised error. Do not only check that the call runs.
- Keep every existing test.
- Change production code only when a value is hard-coded and cannot be passed in. Add an argument with the old value as the default.
- Touch at most one production file and one test file in a round.
- Do not add dependencies.
