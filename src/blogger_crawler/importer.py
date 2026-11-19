from pathlib import Path

from openpyxl import load_workbook

from .models import Blogger


HEADER_ALIASES = {
    "red_id": {"red_id", "博主ID", "博主id", "博主ID"},
    "nickname": {"nickname", "昵称", "昵称备注"},
    "group_name": {"group_name", "分组", "分类"},
    "remark": {"remark", "备注"},
}


def _normalize_header(value: object) -> str:
    return str(value or "").strip()


def _header_map(headers: list[object]) -> dict[str, int]:
    normalized = [_normalize_header(header) for header in headers]
    result: dict[str, int] = {}
    for field, aliases in HEADER_ALIASES.items():
        for index, header in enumerate(normalized):
            if header in aliases:
                result[field] = index
                break
    if "red_id" not in result:
        raise ValueError("Blogger list must include a red_id or 博主ID column.")
    return result


def _cell(row: tuple[object, ...], mapping: dict[str, int], field: str) -> str | None:
    index = mapping.get(field)
    if index is None or index >= len(row):
        return None
    value = row[index]
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip() if value is not None else ""
    return text or None


def validate_bloggers(bloggers: list[Blogger]) -> None:
    if not bloggers:
        raise ValueError("Blogger list is empty.")

    seen: dict[str, str] = {}
    for blogger in bloggers:
        red_id = blogger.red_id.strip()
        if not red_id:
            raise ValueError("Blogger red_id cannot be empty.")
        if len(red_id) > 64:
            raise ValueError(f"red_id is too long: {red_id}")
        if any(character.isspace() for character in red_id):
            raise ValueError(f"red_id cannot contain whitespace: {red_id}")
        normalized = red_id.casefold()
        if normalized in seen:
            raise ValueError(f"Duplicate red_id: {red_id}")
        seen[normalized] = red_id


def load_bloggers(path: str | Path, sheet_name: str = "blogger_list") -> list[Blogger]:
    workbook_path = Path(path)
    if not workbook_path.exists():
        raise FileNotFoundError(f"Blogger list not found: {workbook_path}")

    workbook = load_workbook(workbook_path, data_only=True)
    worksheet = workbook[sheet_name] if sheet_name in workbook.sheetnames else workbook.active
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return []

    mapping = _header_map(list(rows[0]))
    bloggers: list[Blogger] = []
    for row_number, row in enumerate(rows[1:], start=2):
        red_id = _cell(row, mapping, "red_id")
        if not red_id:
            continue
        bloggers.append(
            Blogger(
                red_id=red_id,
                nickname=_cell(row, mapping, "nickname"),
                group_name=_cell(row, mapping, "group_name"),
                remark=_cell(row, mapping, "remark"),
            )
        )
    validate_bloggers(bloggers)
    return bloggers
