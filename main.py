import os, re, html, smtplib, httpx, fitz
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from dotenv import load_dotenv
import arxiv
from data_model import PaperItem, PaperDigest
from collections import defaultdict

load_dotenv()

# env
CATEGORY = os.getenv("ARXIV_CATEGORY", "cs.CR")
LOOKBACK_HOURS = int(os.getenv("ARXIV_LOOKBACK_HOURS", "168"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
MAIL_TO = os.getenv("MAIL_TO", SMTP_USER)
MAIL_TO_LIST = [addr.strip() for addr in MAIL_TO.split(",") if addr.strip()]
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def fetch_recent_arxiv(category: str, lookback_hours: int) -> list[PaperItem]:
    """'Fetch recent arXiv papers in the given category within the lookback hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    search = arxiv.Search(
        query=f"cat:{category}",
        max_results=200,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    client = arxiv.Client(page_size=100, delay_seconds=2.0)
    papers_by_day = defaultdict(list)

    try:
        for result in client.results(search):
            updated = result.updated or result.published
            if updated < cutoff:
                continue
            day = updated.date()
            authors = [a.name for a in result.authors]
            affs = [
                a.affiliation for a in result.authors if getattr(a, "affiliation", None)
            ]
            item = PaperItem(
                arxiv_id=result.get_short_id(),
                title=result.title.strip(),
                summary=result.summary.strip(),
                authors=authors,
                affiliations=list(dict.fromkeys(affs)),
                pdf_url=result.pdf_url.replace("http://", "https://"),
                abs_url=result.entry_id,
            )
            papers_by_day[day].append(item)
    except arxiv.UnexpectedEmptyPageError:
        print("last page reached or no more results.")

    if not papers_by_day:
        return []

    latest_day = max(papers_by_day.keys())
    latest_papers = papers_by_day[latest_day]

    print(f"latest_day: {latest_day}, total papers: {len(latest_papers)}")
    return latest_papers


def extract_main_figure(pdf_bytes: bytes) -> bytes | None:
    """Extract the main figure from the PDF bytes."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        best, best_area = None, 0
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                if pix.alpha or pix.n > 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                w, h = pix.width, pix.height
                area = w * h
                if min(w, h) < 200:
                    continue
                if w / h > 6 or h / w > 6:
                    continue
                if area > best_area:
                    best_area, best = area, pix
        if best:
            return best.tobytes("png")
    except Exception:
        pass
    return None


def build_email(digests):
    msg = MIMEMultipart("related")
    msg["Subject"] = (
        f"[arXiv {CATEGORY}] 每日摘要（{datetime.now().strftime('%Y-%m-%d')}）"
    )
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(MAIL_TO_LIST)

    html_blocks, img_attachments = [], []
    for i, d in enumerate(digests, 1):
        p = d.paper
        block = f"""
        <h3>{i}. {html.escape(p.title)}</h3>
        <p><b>作者：</b>{html.escape(', '.join(p.authors))}<br/>
        <a href="{p.abs_url}">摘要页</a> | <a href="{p.pdf_url}">PDF</a></p>
        <p style="white-space: pre-line;">{html.escape(d.zh_summary)}</p>
        """

        # if d.main_img_bytes and d.main_img_cid:
        #     block += (
        #         f'<p><img src="cid:{d.main_img_cid}" style="max-width:720px;"/></p>'
        #     )
        #     img_attachments.append((d.main_img_cid, d.main_img_bytes))

        html_blocks.append(block)

    html_body = f"""
    <html><body>
    <h2>arXiv {CATEGORY} 每日摘要</h2>
    {''.join(html_blocks) or '<p>今日暂无新论文。</p>'}
    <hr/><p style="color:#888">Gemini 自动生成 · 请核对原文。</p></body></html>
    """

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("请使用 HTML 邮件查看。", "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    for cid, b in img_attachments:
        img = MIMEImage(b, "png")
        img.add_header("Content-ID", f"<{cid}>")
        msg.attach(img)

    return msg


def send_email(msg):
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, MAIL_TO_LIST, msg.as_string())


def extract_affiliations_from_pdf(pdf_bytes: bytes) -> list[str]:
    affiliations = set()
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = doc[0].get_text("text")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        for line in lines:
            if re.match(r"^\d+\s*[-–:]?\s*", line):
                if any(
                    k in line.lower()
                    for k in [
                        "university",
                        "institute",
                        "college",
                        "lab",
                        "centre",
                        "center",
                    ]
                ):
                    affiliations.add(line)

        if not affiliations:
            for line in lines:
                if any(
                    k in line.lower()
                    for k in ["university", "institute", "college", "academy", "lab"]
                ):
                    affiliations.add(line)

        cleaned = []
        for aff in affiliations:
            aff = re.sub(r"^\d+\s*[-–:]?\s*", "", aff).strip()
            aff = re.sub(r"\s+", " ", aff)
            cleaned.append(aff)

        return list(dict.fromkeys(cleaned))

    except Exception:
        return []


def summarize_from_pdf(paper):
    import os, httpx, tempfile, google.generativeai as genai, fitz

    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    pdf_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf_path = tmp.name
            with httpx.Client(timeout=30) as client:
                r = client.get(paper.pdf_url)
                r.raise_for_status()
                tmp.write(r.content)

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        affiliations = extract_affiliations_from_pdf(pdf_bytes)

        text = []
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text.append(page.get_text("text"))
        full_text = "\n".join(text)

        aff_text = ", ".join(affiliations) if affiliations else "the research team"
        prompt = f"""
You are an expert academic summarizer.
Based on the following paper content, write a concise summary (1-2 paragraphs) in English.
The summary should start with: "{aff_text} ..." describing what they did, and naturally include the motivation, method, and results.
Write in formal academic English.

Title: {paper.title}
Authors: {', '.join(paper.authors)}
Affiliations: {aff_text}
Paper Content:
{full_text[:20000]}
"""
        response = model.generate_content(prompt)
        summary_en = response.text.strip()

        zh_prompt = (
            "将以下英文研究总结翻译成流畅、正式的学术中文，并保留专业术语。保持开头格式不变：\n\n"
            f"{summary_en}"
        )
        zh_response = model.generate_content(zh_prompt)
        zh_summary = zh_response.text.strip()

        return zh_summary

    finally:
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)


def run():
    papers = fetch_recent_arxiv(CATEGORY, LOOKBACK_HOURS)
    digests = []
    for p in papers:
        print(f"total papers fetched: {len(papers)}, processing paper: {p.arxiv_id}")
        zh_summary = summarize_from_pdf(p)
        img = None
        try:
            with httpx.Client(timeout=20) as client:
                r = client.get(p.pdf_url)
                r.raise_for_status()
                img = extract_main_figure(r.content)
        except Exception:
            pass

        cid = f"img-{p.arxiv_id}"
        digests.append(
            PaperDigest(
                paper=p,
                zh_summary=zh_summary,
                main_img_bytes=img,
                main_img_cid=cid if img else None,
            )
        )

    msg = build_email(digests)

    for part in msg.walk():
        if part.get_content_type() == "text/html":
            html_content = part.get_payload(decode=True).decode(
                part.get_content_charset()
            )
            with open("arxiv_daily.html", "w", encoding="utf-8") as f:
                f.write(html_content)

    print("has written arxiv_daily.html for preview.")
    send_email(msg)


if __name__ == "__main__":
    run()
