"""Word, PowerPoint and Excel files become knowledge text, safely."""
import io
import zipfile

import pytest

from northcx.ingest import IngestError, extract, sniff

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def zipped(files: dict[str, str]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in files.items():
            z.writestr(k, v)
    return b.getvalue()


def docx(body: str, title: str = "") -> bytes:
    files = {"word/document.xml": f"<w:document {W}><w:body>{body}</w:body></w:document>"}
    if title:
        files["docProps/core.xml"] = f'<cp:coreProperties xmlns:cp="x" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title></cp:coreProperties>'
    return zipped(files)


def p(text, style=None, bullet=False):
    ppr = (f'<w:pStyle w:val="{style}"/>' if style else "") + ("<w:numPr/>" if bullet else "")
    return f"<w:p><w:pPr>{ppr}</w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>"


async def test_word_headings_lists_and_tables_become_structured_text():
    data = docx(p("Returns policy", "Heading1") + p("Items can be returned within 30 days.") + p("Keep the receipt", bullet=True)
                + "<w:tbl><w:tr><w:tc>" + p("Item") + "</w:tc><w:tc>" + p("Days") + "</w:tc></w:tr><w:tr><w:tc>" + p("Shoes") + "</w:tc><w:tc>" + p("30") + "</w:tc></w:tr></w:tbl>", "Acme returns")
    ex = await extract(data, "returns.docx")
    assert ex.kind == "docx" and ex.title == "Acme returns"
    assert "# Returns policy" in ex.text and "- Keep the receipt" in ex.text and "Shoes | 30" in ex.text and sniff(data) == "docx"


async def test_powerpoint_reads_slides_in_order_and_skips_notes():
    slide = lambda t: f"<p:sld {A} xmlns:p='p'><a:p><a:r><a:t>{t}</a:t></a:r></a:p><a:p><a:r><a:t>detail for {t}</a:t></a:r></a:p></p:sld>"  # noqa: E731
    data = zipped({"ppt/slides/slide10.xml": slide("Tenth"), "ppt/slides/slide2.xml": slide("Second"), "ppt/notesSlides/notesSlide2.xml": slide("PRIVATE NOTE")})
    ex = await extract(data, "deck.pptx")
    assert ex.kind == "pptx" and ex.text.index("Second") < ex.text.index("Tenth") and "PRIVATE" not in ex.text


async def test_excel_reads_visible_sheets_with_shared_strings():
    data = zipped({
        "xl/workbook.xml": f'<workbook {S} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Prices" sheetId="1" r:id="rId1"/><sheet name="Secret" sheetId="2" state="hidden" r:id="rId2"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>',
        "xl/sharedStrings.xml": f"<sst {S}><si><t>Plan</t></si><si><t>Basic</t></si></sst>",
        "xl/worksheets/sheet1.xml": f'<worksheet {S}><sheetData><row><c t="s"><v>0</v></c><c><v>Price</v></c></row><row><c t="s"><v>1</v></c><c><v>9.99</v></c></row></sheetData></worksheet>',
        "xl/worksheets/sheet2.xml": f'<worksheet {S}><sheetData><row><c t="inlineStr"><is><t>hidden data</t></is></c></row></sheetData></worksheet>'})
    ex = await extract(data, "prices.xlsx")
    assert ex.kind == "xlsx" and "## Prices" in ex.text and "Basic | 9.99" in ex.text and "hidden data" not in ex.text


@pytest.mark.parametrize("name,data", [
    ("entity", docx("<w:p><w:r><w:t>x</w:t></w:r></w:p>").replace(b"<w:document", b"<!DOCTYPE d [<!ENTITY a 'aaaa'>]><w:document", 1)),
    ("not office", zipped({"readme.txt": "hello"})),
    ("garbage zip", b"PK\x03\x04" + b"\x00" * 50),
    ("empty doc", docx("")),
    ("broken xml", zipped({"word/document.xml": "<w:document"})),
])
async def test_hostile_or_damaged_files_are_refused_cleanly(name, data):
    with pytest.raises(IngestError):
        await extract(data, "x.docx")


async def test_a_zip_bomb_is_refused_before_unpacking():
    bomb = zipped({"word/document.xml": "<w:document " + W + "><w:body>" + "<w:p/>" * 3_000_000 + "</w:body></w:document>"})
    with pytest.raises(IngestError):
        await extract(bomb, "bomb.docx")
