"""把图片序列写成 PDF（直接嵌入 JPEG 流，内存占用低、速度快）。

不依赖 reportlab / img2pdf，只用 Pillow 解码 + 自写的极简 PDF 写入器。
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps


def _prepare_image(path, quality: int, max_width: int):
    """把任意图片转成 (jpeg_bytes, width, height, colorspace)。"""
    with Image.open(path) as im:
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        im.load()

        if im.mode in ("RGBA", "LA", "P", "PA"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode == "CMYK":
            im = im.convert("RGB")
        elif im.mode not in ("RGB", "L"):
            im = im.convert("RGB")

        if max_width and im.width > max_width:
            height = max(1, round(im.height * max_width / im.width))
            im = im.resize((max_width, height), Image.LANCZOS)

        buf = io.BytesIO()
        if im.mode == "L":
            im.save(buf, "JPEG", quality=quality, optimize=True)
            colorspace = "DeviceGray"
        else:
            im.save(buf, "JPEG", quality=quality, optimize=True)
            colorspace = "DeviceRGB"
        return buf.getvalue(), im.width, im.height, colorspace


def _pdf_text(text: str) -> bytes:
    return b"<FEFF" + str(text).encode("utf-16-be").hex().upper().encode() + b">"


class _Writer:
    def __init__(self, fp):
        self.fp = fp
        self.offsets: dict[int, int] = {}

    def obj(self, num: int, body: bytes) -> None:
        self.offsets[num] = self.fp.tell()
        self.fp.write(f"{num} 0 obj\n".encode())
        self.fp.write(body)
        self.fp.write(b"\nendobj\n")

    def stream(self, num: int, dict_body: str, data: bytes) -> None:
        self.offsets[num] = self.fp.tell()
        self.fp.write(f"{num} 0 obj\n".encode())
        self.fp.write(f"<< {dict_body} /Length {len(data)} >>\nstream\n".encode())
        self.fp.write(data)
        self.fp.write(b"\nendstream\nendobj\n")


def build_pdf(
    image_paths,
    out_path,
    quality: int = 92,
    max_width: int = 0,
    title: str = "",
    on_progress=None,
    on_skip=None,
) -> tuple[Path, int]:
    """生成 PDF，返回 (路径, 实际页数)。损坏图片会被跳过。"""
    paths = [Path(p) for p in image_paths]
    total = len(paths)
    if total == 0:
        raise ValueError("没有可用的图片")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(out_path.name + ".part")

    pages: list[int] = []
    written = 0

    try:
        with open(tmp_path, "wb") as fp:
            w = _Writer(fp)
            fp.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
            w.obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")

            for index, path in enumerate(paths):
                try:
                    jpeg, iw, ih, colorspace = _prepare_image(path, quality, max_width)
                except Exception as e:
                    if on_skip is not None:
                        on_skip(path, e)
                    continue

                base = 3 + 3 * written
                image_id, content_id, page_id = base, base + 1, base + 2
                w.stream(
                    image_id,
                    f"/Type /XObject /Subtype /Image /Width {iw} /Height {ih} "
                    f"/ColorSpace /{colorspace} /BitsPerComponent 8 /Filter /DCTDecode",
                    jpeg,
                )
                content = f"q\n{iw} 0 0 {ih} 0 0 cm\n/Im0 Do\nQ\n".encode()
                w.stream(content_id, "", content)
                w.obj(
                    page_id,
                    (
                        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {iw} {ih}] "
                        f"/Resources << /XObject << /Im0 {image_id} 0 R >> >> "
                        f"/Contents {content_id} 0 R >>"
                    ).encode(),
                )
                pages.append(page_id)
                written += 1
                if on_progress is not None:
                    on_progress(index + 1, total)

            if written == 0:
                raise ValueError("所有图片都无法解码")

            kids = b" ".join(f"{pid} 0 R".encode() for pid in pages)
            w.obj(2, b"<< /Type /Pages /Count %d /Kids [%s] >>" % (written, kids))

            info_id = 3 + 3 * written
            info = b"<< /Producer (JMComic Client) /Title " + _pdf_text(
                title or out_path.stem
            ) + b" >>"
            w.obj(info_id, info)

            max_id = info_id
            xref_at = fp.tell()
            fp.write(f"xref\n0 {max_id + 1}\n".encode())
            fp.write(b"0000000000 65535 f \n")
            for num in range(1, max_id + 1):
                offset = w.offsets.get(num)
                if offset is None:
                    fp.write(b"0000000000 65535 f \n")
                else:
                    fp.write(f"{offset:010d} 00000 n \n".encode())
            fp.write(
                (
                    f"trailer\n<< /Size {max_id + 1} /Root 1 0 R /Info {info_id} 0 R >>\n"
                    f"startxref\n{xref_at}\n%%EOF\n"
                ).encode()
            )
        tmp_path.replace(out_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass

    return out_path, written
