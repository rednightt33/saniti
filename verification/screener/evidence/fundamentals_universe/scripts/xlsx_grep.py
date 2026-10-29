import sys, re, openpyxl
wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
pat = re.compile(r'fundament|market cap|universe|sector|industry|board|LQ45|liquid|free float|notation|suspend', re.I)
print('sheets:', wb.sheetnames)
for ws in wb.worksheets:
    for row in ws.iter_rows(values_only=True):
        for c in row:
            if isinstance(c, str) and pat.search(c):
                print(ws.title, '|', c[:300].replace('\n', ' '))
