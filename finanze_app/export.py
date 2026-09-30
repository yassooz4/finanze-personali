"""Excel exports are copies, never the production database."""
from io import BytesIO
from openpyxl import Workbook
from .storage import SCHEMA, ExcelStore


def excel_export(tables):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, schema in SCHEMA.items():
        sheet = workbook.create_sheet(name)
        headers = list(schema)
        for record in tables[name]:
            headers.extend(key for key in record if key not in headers)
        sheet.append(headers)
        for record in tables[name]:
            sheet.append([record.get(key) for key in headers])
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.data_type = "s"
        ExcelStore._style(sheet)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
