# Market analytics worker

This isolated Railway service executes one generic, bounded analytical SQL job over
immutable snapshots created by `market-ai-backend`. It has no PostgreSQL URL and no
raw/Feature-table credentials. Its only secret is a dedicated internal worker token;
the backend provides a short-lived URL for the exact leased snapshot.

The worker accepts only one `SELECT`/`WITH` statement over snapshot dataset names.
External access and file/database attachment are disabled, dangerous statements and
reader functions are rejected, and memory, runtime, result-row, and result-byte caps
are enforced. Method-specific logic such as event studies, forward returns, streaks,
regression, or clustering can be expressed inside this single controlled computation
surface without adding a model-facing tool for each investment question.

