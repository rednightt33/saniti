import sys, openpyxl
wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
ids = {f'I{i:02d}' for i in range(1, 28)}
ws = wb['02_PARAMETERS']; rows = list(ws.iter_rows(values_only=True))
print('== 02_PARAMETERS (ID, key, param, default, evidence, min, max, note)')
for r in rows[1:]:
    if r[0] in ids: print(r[0], r[1], r[2], repr(r[6]), r[7], r[8], r[9], '|', (r[14] or '')[:160])
ws = wb['01_INDICATORS']; rows = list(ws.iter_rows(values_only=True))
print('== 01_INDICATORS (ID, key, data, outputs, pine, readiness, note)')
for r in rows[1:]:
    if r[0] in ids: print(r[0], r[3], r[4], '|', r[6], '|', r[7], '|', r[9], '|', (r[10] or '')[:200])
ws = wb['03_CALCULATIONS']; rows = list(ws.iter_rows(values_only=True))
print('== 03_CALCULATIONS (ID, outline, parity risk, status)')
for r in rows[1:]:
    if r[0] in ids: print(r[0], r[1], '|', (r[2] or '')[:260], '|| risk:', (r[6] or '')[:220], '|', r[7])
