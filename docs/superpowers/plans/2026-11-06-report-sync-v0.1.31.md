# Synchronize report behavior from upstream v0.1.31

**Goal:** Port the report changes requested by the user from upstream v0.1.31, commit verified source to origin/development, and preserve the original Tk UI, Rust backend and platform-specific update channels.

**Pinned upstream:** `43edde1bd90149c8474e673319423f0275531fe7` (`upstream-v0.1.31`), not the moving upstream/main.

**Approach:** Integrate report behavior and its tests in the existing modules. Adapt upstream shared imports to this branch's root toolbox modules; do not import the unrelated shared-package refactor, private-upload feature, topology editor or macOS installation changes. Independent morning-report and market-daily work is delegated under the parallel-agents skill. AGENTS.md authorizes direct implementation and development synchronization.

## Exact contracts

- Morning report D-1: `快报` J8/J13/J19 for thermal online energy, Qingyuan residual J7 minus those three, renewable K values by label; total J7 plus renewable energy. Prices use the same workbook's day-ahead sheet G7/G8/G13/G19 and renewable H values.
- Morning report D: day-ahead energy includes F7, renewable G totals and `(基础信息!AA64 + AC64)/10` in 万千瓦时; strategies come from day-ahead A39, with label-based fallback; unit status is read from 基础信息 C, Dongguan listed in suite order. D-1 statuses supply comparisons.
- Morning report D-2: 24-column daily-clearing Word table, 11 logical rows, thermal D/E,F/G,H/I,J,L/M,O,P:R,S:U,V:X,Y:AA,AE and renewable C,E/F,G/H,I/J,K,M/N,O/P,S,T:V,W:Y,AB mapped exactly as upstream. Missing values remain `/`; half-up integer formatting and negative-zero behavior follow upstream. Spot-deviation analysis uses the explicit real-time fields/rows and skips unreleased all-zero data.
- Workbook A2 dates are audited against D-1/D/D-2; missing content preserves template text and reports an audit reason. Automatic filename matching must distinguish November 1 from November 10 and accept zero padding.
- Preserve the existing A4 template; keep daily-clearing/forecast headings with tables and fit the forecast to a single A4 page. Negative daily-clearing amounts are red, zero/negative zero are not, spot-deviation body stays uncolored.
- Market daily D report date is derived read-only from the selected D workbook; changing its date clears manual supplements. GUI and service/CLI must agree. CLI explicit dates remain supported and validated before network requests. D-1/D-2 mappings remain unchanged. Strategies split into three named plants; preserve region lead-in text without a region heading.

## Work

- [x] Capture upstream tests and observe failures before implementation.
- [x] Port morning report core/template/mapping changes while keeping Windows and independent authentication adapters.
- [x] Port market daily date inference and strategy splitting across GUI, service and CLI while retaining native implementations and prior duplicate-field removal.
- [x] Add regression coverage for exact date filenames, full-width sheet parentheses, stale async results and destroyed-page cleanup.
- [x] Generate synthetic report outputs and read back key workbook/Word values, formats, audit fields and PDF/layout where available; never overwrite real user inputs or use real credentials.
- [x] Run relevant regressions, review changes, update CHANGELOG and synchronize development; clearly distinguish source delivery from any separately verified installer release.

219 targeted checks passed; review findings on missing-energy handling and blank-paragraph content preservation were fixed. Actual Word rendering passed on five A4 pages. Evidence: `docs/report-sync-v0.1.31-validation.md`. Deliverable: verified development source, not a new installer release.

## Verification limits

Use temporary synthetic workbooks/documents and mocked network responses. No real website uploads or report submission are authorized by this source-sync request. Preserve existing application configuration, login state, browser profiles and user templates. Any Windows 10/macOS or document-rendering environment limitation must be reported explicitly.
