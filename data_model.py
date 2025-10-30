from pydantic import BaseModel


class PaperItem(BaseModel):
    arxiv_id: str
    title: str
    summary: str
    authors: list[str]
    pdf_url: str
    abs_url: str


class PaperDigest(BaseModel):
    paper: PaperItem
    zh_summary: str
    summary_en: str
    main_img_bytes: bytes | None
    main_img_cid: str | None
