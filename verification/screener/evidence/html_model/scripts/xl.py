import sys, openpyxl
wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
for ws in wb.worksheets:
    rows = list(ws.iter_rows(values_only=True))
    print('==', ws.title, len(rows), 'rows')
    for r in rows[:4]:
        print('  ', [str(c)[:60] if c is not None else None for c in r][:14])
