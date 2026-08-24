# First North source-profile rejection

The generic `Equity_Trading_by_Company_and_Instrument_YYMM` attachments returned by the Nasdaq notices API are not accepted as First North merely because they appeared under a First North-related notice group. All 200 downloaded workbooks expose Main Market fields (`Company Code`, `Location`) and Main Market segments (`Large Cap`, `Mid Cap`, `Small Cap`).

The verified First North sample instead contains `First North Trading Details`, uses `Issuer Code`, and has no `Location` field. The ingestion parser now enforces this signature. The prior extracted rows, intervals, mappings and identity results are quarantined as invalid and cannot be consumed by OTSC1 or any canonical universe.

No Main Market artifact or production data was changed.
