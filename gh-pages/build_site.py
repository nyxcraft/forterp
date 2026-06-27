#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import unicodedata
from html import escape
from pathlib import Path

try:
    from markdown_it import MarkdownIt
except ImportError as exc:  # pragma: no cover - human setup path
    raise SystemExit(
        "markdown-it-py is required to build the docs site.\n"
        "Install it with: pip install markdown-it-py"
    ) from exc


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "gh-pages"  # build machinery: site.json, templates/, assets/
OUTPUT_DIR = ROOT / "gh-pages" / "public"  # built site (gitignored; published by Actions)
HEADER_LOGO = "assets/logo-forterp.svg"


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or "section"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def render_template(path: Path, context: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in context.items():
        text = text.replace(f"{{{{ {key} }}}}", value)
    return text


def relative_href(from_file: Path, to_file: Path) -> str:
    return os.path.relpath(to_file, from_file.parent).replace(os.sep, "/")


class MarkdownRenderer:
    def __init__(self) -> None:
        self.md = MarkdownIt("commonmark", {"html": True, "typographer": True})
        self.md.enable("table")
        self.md.enable("strikethrough")

    def render(self, text: str) -> dict[str, object]:
        tokens = self.md.parse(text)
        slug_counts: dict[str, int] = {}
        toc: list[dict[str, object]] = []
        title = None
        first_h1_index = None

        for index, token in enumerate(tokens):
            if token.type != "heading_open":
                continue
            level = int(token.tag[1])
            if index + 1 >= len(tokens):
                continue
            inline = tokens[index + 1]
            if inline.type != "inline":
                continue
            heading_text = inline.content.strip()
            if not heading_text:
                continue

            base_slug = slugify(heading_text)
            count = slug_counts.get(base_slug, 0)
            slug_counts[base_slug] = count + 1
            anchor = base_slug if count == 0 else f"{base_slug}-{count + 1}"
            token.attrSet("id", anchor)

            if level == 1 and title is None:
                title = heading_text
                first_h1_index = index
            elif level in (2, 3):
                toc.append({"level": level, "anchor": anchor, "text": heading_text})

        if first_h1_index is not None:
            del tokens[first_h1_index : first_h1_index + 3]

        html = self.md.renderer.render(tokens, self.md.options, {})
        return {"title": title, "toc": toc, "html": html}


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_tree(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def rewrite_md_links(
    html: str,
    current_output: Path,
    output_dir: Path,
    basename_to_output: dict[str, str],
    current_source: str | None = None,
    source_to_output: dict[str, str] | None = None,
) -> str:
    """Rewrite `<a href="...md">` links so cross-document links work in the built site too.

    The Markdown sources use ordinary relative `.md` links (e.g. `[DESIGN.md](DESIGN.md)`) so
    they also resolve when browsed on GitHub. Here we map each `.md` target to the corresponding
    page's pretty URL, made relative to the page being written, preserving any `#anchor`.

    Resolution is **path-aware** first: the link is resolved relative to the current page's source
    directory and looked up by repo-relative path (so a multi-file manual's `05-foo.md`,
    `../API.md`, and two README.md files all map correctly). It falls back to a basename match for
    plain same-folder links, and leaves links to non-page `.md` files untouched."""

    def replace(match: re.Match[str]) -> str:
        href = match.group(1)
        if "://" in href or href.startswith(("#", "mailto:")):
            return match.group(0)
        path, _, anchor = href.partition("#")
        target = None
        if path and current_source is not None and source_to_output is not None:
            resolved = os.path.normpath(os.path.join(os.path.dirname(current_source), path))
            target = source_to_output.get(resolved.replace(os.sep, "/"))
        if target is None:
            target = basename_to_output.get(os.path.basename(path).lower())
        if target is None:
            return match.group(0)
        suffix = "#" + anchor if anchor else ""
        rel = relative_href(current_output, output_dir / target)
        return f'href="{escape(rel + suffix)}"'

    return re.sub(r'href="([^"]+\.md(?:#[^"]*)?)"', replace, html)


def first_heading(path: Path) -> str | None:
    """The text of a Markdown file's first level-1 heading (`# Title`), for auto-titling pages."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


INCLUDE_LANGS = {
    ".py": "python",
    ".sh": "bash",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".js": "javascript",
    ".css": "css",
    ".html": "html",
}


def expand_includes(text: str) -> str:
    """Expand `<!--include: path-->` (path relative to the repo root) into a fenced code block
    of that file's current contents -- so demo source lives in one runnable place (demos/)
    and is shown on the page without copy-paste drift. Runs before Markdown rendering."""

    def replace(match: re.Match[str]) -> str:
        rel = match.group(1).strip()
        try:
            body = (ROOT / rel).read_text(encoding="utf-8").rstrip("\n")
        except OSError:
            return match.group(0)  # leave the directive untouched if the file is missing
        lang = INCLUDE_LANGS.get(Path(rel).suffix, "")
        return f"```{lang}\n{body}\n```"

    return re.sub(r"<!--\s*include:\s*([^>]+?)\s*-->", replace, text)


def rewrite_img_src(html: str, current_output: Path, output_dir: Path) -> str:
    """Rewrite content `<img src="...">` -- authored relative to docs/ (e.g. `media/foo.png`,
    which also resolves on GitHub) -- to a path relative to the page being written. The
    `docs/media/` tree is copied to `<site>/media/` at build time."""

    def replace(match: re.Match[str]) -> str:
        src = match.group(1)
        if "://" in src or src.startswith(("/", "data:")):
            return match.group(0)
        norm = src[2:] if src.startswith("./") else src
        return f'src="{escape(relative_href(current_output, output_dir / norm))}"'

    return re.sub(r'src="([^"]+)"', replace, html)


def build_toc(entries: list[dict[str, object]]) -> str:
    if not entries:
        return ""
    items = []
    for entry in entries:
        level = int(entry["level"])
        cls = f"section-nav__link section-nav__link--l{level}"
        items.append(
            f'<li><a class="{cls}" href="#{escape(str(entry["anchor"]))}">'
            f"{escape(str(entry['text']))}</a></li>"
        )
    return '<ul class="section-nav__list">\n' + "\n".join(items) + "\n</ul>"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the forterp docs site.")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="Build output directory")
    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    config = read_json(SOURCE_DIR / "site.json")
    renderer = MarkdownRenderer()

    ensure_clean_dir(output_dir)
    copy_tree(SOURCE_DIR / "assets", output_dir / "assets")
    # cache-buster: a short content hash on the stylesheet URL, so an edited site.css is
    # re-fetched instead of served stale from the browser cache.
    css_ver = hashlib.sha1((SOURCE_DIR / "assets" / "site.css").read_bytes()).hexdigest()[:8]
    copy_tree(ROOT / "docs" / "media", output_dir / "media")  # screenshots/gifs for the reference
    write_text(output_dir / ".nojekyll", "")

    docs_pages: list[dict[str, str]] = []
    for entry in config["docs"]:
        docs_pages.append(
            {
                "slug": entry["slug"],
                "title": entry["title"],
                "summary": entry["summary"],
                "source": entry["source"],
                "template": entry.get("template", "doc"),  # "doc" (section viewer) or "page"
                "output": str(Path(entry["slug"]) / "index.html"),
                "featured": bool(entry.get("featured", False)),
            }
        )
        # A multi-file manual: an entry may name a `chapters` directory whose other *.md files are
        # auto-rendered as sub-pages (slug `<entry>/<stem>`), titled from each file's first heading.
        # Keeps site.json small and picks up new chapters automatically; they are not featured (so
        # they don't crowd the home cards) but are fully rendered and cross-linked.
        chapters_dir = entry.get("chapters")
        if chapters_dir:
            for md in sorted((ROOT / chapters_dir).glob("*.md")):
                if md.name.lower() == "readme.md":
                    continue  # the index is the entry's own `source`
                stem = md.stem
                docs_pages.append(
                    {
                        "slug": f"{entry['slug']}/{stem}",
                        "title": first_heading(md) or stem,
                        "summary": "",
                        "source": str(md.relative_to(ROOT)).replace(os.sep, "/"),
                        "template": entry.get("template", "doc"),
                        "output": str(Path(entry["slug"]) / stem / "index.html"),
                        "featured": False,
                    }
                )

    for page in docs_pages:
        page["href"] = page["output"].replace(os.sep, "/")

    # Path-aware link map: repo-relative source path -> built output (unique per file, so two
    # different README.md files don't collide). The render loop resolves each `.md` link relative
    # to its own source directory and looks it up here.
    source_to_output = {p["source"].replace(os.sep, "/"): p["output"] for p in docs_pages}

    # Basename fallback for plain same-folder links and links to README (not a page of its own;
    # point those at the home page).
    basename_to_output = {os.path.basename(p["source"]).lower(): p["output"] for p in docs_pages}
    basename_to_output.setdefault("readme.md", "index.html")

    featured_pages = [page for page in docs_pages if page["featured"]] or docs_pages
    docs_cards = []
    for page in featured_pages:
        docs_cards.append(
            "\n".join(
                [
                    '<article class="doc-card">',
                    f'  <h3><a href="{escape(page["href"])}">{escape(page["title"])}</a></h3>',
                    f"  <p>{escape(page['summary'])}</p>",
                    f'  <a class="doc-card__link" href="{escape(page["href"])}">Open</a>',
                    "</article>",
                ]
            )
        )

    # The "Docs" link in every header points at the index page (rendered from docs/README.md);
    # fall back to the first page if no explicit index is configured.
    index_page = next((p for p in docs_pages if p["slug"] == "docs"), docs_pages[0])
    # The "Reference" link in every header points at the reference page, if there is one.
    reference_page = next((p for p in docs_pages if p["slug"] == "reference"), None)
    # The footer's "MIT-licensed" links to the license page, if there is one.
    license_page = next((p for p in docs_pages if p["slug"] == "license"), None)
    content_pages = [p for p in docs_pages if p is not index_page]
    hero_primary = content_pages[0]["href"] if content_pages else "#"  # "Get started" -> guide
    hero_secondary = content_pages[1]["href"] if len(content_pages) > 1 else hero_primary
    github_href = config.get("github_href", "#")
    year = str(datetime.date.today().year)
    copyright_holder = config.get("copyright", config["site_name"])
    # An optional status stamp ("beta") shown next to the brand on every page; omit the key to drop
    status = config.get("status")
    status_badge = f'<span class="brand__badge">{escape(status)}</span>' if status else ""
    # Author / coding-attribution lines (site.json "attribution"), shown verbatim in the footer
    # on every page and, on the home page, above the fold in the hero. Each line on its own line.
    attribution_lines = config.get("attribution") or []
    attribution = (
        '<p class="site-footer__attr">'
        + "<br>".join(escape(line) for line in attribution_lines)
        + "</p>"
        if attribution_lines
        else ""
    )
    attribution_hero = (
        '<div class="hero__attr">'
        + "".join(f"<p>{escape(line)}</p>" for line in attribution_lines)
        + "</div>"
        if attribution_lines
        else ""
    )

    home_html = render_template(
        SOURCE_DIR / "templates" / "home.html",
        {
            "site_name": escape(config["site_name"]),
            "site_tagline": escape(config["site_tagline"]),
            "site_description": escape(config["site_description"]),
            "stylesheet": escape(f"assets/site.css?v={css_ver}"),
            "logo_href": escape(HEADER_LOGO),
            "home_href": escape("index.html"),
            "status_badge": status_badge,
            "github_href": escape(github_href),
            "docs_href": escape(
                relative_href(output_dir / "index.html", output_dir / index_page["output"])
            ),
            "reference_href": escape(
                relative_href(output_dir / "index.html", output_dir / reference_page["output"])
                if reference_page
                else "#"
            ),
            "primary_href": escape(hero_primary),
            "secondary_href": escape(hero_secondary),
            "docs_cards": "\n".join(docs_cards),
            "year": year,
            "copyright": escape(copyright_holder),
            "attribution": attribution,
            "attribution_hero": attribution_hero,
            "license_href": escape(
                relative_href(output_dir / "index.html", output_dir / license_page["output"])
                if license_page
                else github_href
            ),
        },
    )
    write_text(output_dir / "index.html", home_html)

    for page in docs_pages:
        source_path = ROOT / page["source"]
        rendered = renderer.render(expand_includes(source_path.read_text(encoding="utf-8")))
        output_path = output_dir / page["output"]
        content_html = rewrite_md_links(
            str(rendered["html"]),
            output_path,
            output_dir,
            basename_to_output,
            page["source"].replace(os.sep, "/"),
            source_to_output,
        )
        content_html = rewrite_img_src(content_html, output_path, output_dir)
        toc_html = build_toc(rendered["toc"])  # type: ignore[arg-type]
        asset_href = relative_href(output_path, output_dir / "assets" / "site.css")
        logo_href = relative_href(output_path, output_dir / HEADER_LOGO)
        home_href = relative_href(output_path, output_dir / "index.html")
        docs_href = relative_href(output_path, output_dir / index_page["output"])
        reference_href = (
            relative_href(output_path, output_dir / reference_page["output"])
            if reference_page
            else docs_href
        )
        license_href = (
            relative_href(output_path, output_dir / license_page["output"])
            if license_page
            else github_href
        )
        template = "page.html" if page["template"] == "page" else "doc.html"

        doc_html = render_template(
            SOURCE_DIR / "templates" / template,
            {
                "page_title": escape(page["title"]),
                "site_name": escape(config["site_name"]),
                "site_tagline": escape(config["site_tagline"]),
                "page_summary": escape(page["summary"]),
                "assets_href": escape(f"{asset_href}?v={css_ver}"),
                "logo_href": escape(logo_href),
                "home_href": escape(home_href),
                "status_badge": status_badge,
                "github_href": escape(github_href),
                "docs_href": escape(docs_href),
                "reference_href": escape(reference_href),
                "toc": toc_html,
                "source_title": escape(str(rendered["title"] or "")),
                "content": content_html,
                "year": year,
                "copyright": escape(copyright_holder),
                "attribution": attribution,
                "license_href": escape(license_href),
            },
        )
        write_text(output_path, doc_html)

    print(f"Built site into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
