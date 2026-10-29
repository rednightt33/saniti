import openpyxl, sys
wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
for ws in wb.worksheets:
    rows = list(ws.iter_rows(values_only=True))
    print('=== SHEET', ws.title, len(rows), 'rows')
    for r in rows[:4]:
        print('  ', [str(x)[:40] if x is not None else None for x in r])
