---
name: test
description: Run the project's unit tests and fix any failures. Use after changing Lambda code or tests.
---

Run the unit test suite with `python3.13 -m pytest tests/unit/ -v`.

If any test fails, read the failure output and decide from the specs in `specs/` whether the code or the test is wrong. If the code is wrong, fix it and run the suite again, until every test passes. If you conclude that a test is wrong, stop and explain why before you change it, because each test encodes an acceptance criterion. Report the final result in one line.