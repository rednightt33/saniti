import sys, openpyxl
wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
print(wb.sheetnames)
for name in wb.sheetnames:
    ws = wb[name]
    rows = list(ws.iter_rows(values_only=True))
    print('==', name, len(rows), 'rows; header:', rows[0] if rows else None)
