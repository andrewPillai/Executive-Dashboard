Northstar Scientific frontend

React + TypeScript + Vite client-rendered application. Uses TanStack Query for API
state, TanStack Table for server-paginated orders, Radix Dialog for accessible
dialogs, and Apache ECharts for the monthly sales chart.

Development: pnpm dev (API expected on 127.0.0.1:8000).
Build: pnpm build. FastAPI serves the generated dist directory in local demo mode.

The role selector is a demonstration perspective switch, not authentication or
authorization. Data is synthetic. Recommendations are scripted. Drafts and approved
assignments persist in the local API workflow store; they cause no external writes.
Reset clears workflow drafts/assignments only, not business records.

UI interaction checks:
- Switch among eight roles and inspect their contextual operational metrics.
- Open a case; inspect evidence; draft a response; explicitly approve the assignment.
- Close/reopen or reload: saved draft/assignment remains visible.
- The unfinished-response banner resumes a saved draft.
- Filter cases by manufacturer-direct or warehouse/pricing context.
- Search order lines and change server pages.
- Inspect monthly chart values through the accessible table.
- Filter the 27-site fictional network by region.
- Reset decisions through the confirmation dialog.
