from __future__ import annotations

import re
from dataclasses import dataclass, field


_HEADING_PATTERN = re.compile(r"(?m)^(#{1,6})\s+(.*)$")
_ENDPOINT_PATTERN = re.compile(
    r"(?im)^\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+((?:https?://[^\s`]+)|(?:/[^\s`]+)|(?:[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+/[^\s`]*))"
)


@dataclass(slots=True)
class MarkdownEndpointMatch:
    method: str
    path: str
    line_number: int
    char_start: int
    char_end: int


@dataclass(slots=True)
class MarkdownEndpointSection:
    title: str
    content: str
    chunk_index: int
    endpoints: list[str] = field(default_factory=list)
    endpoint_matches: list[MarkdownEndpointMatch] = field(default_factory=list)
    line_start: int = 1
    line_end: int = 1


@dataclass(slots=True)
class MarkdownEndpointParseResult:
    sections: list[MarkdownEndpointSection]
    section_count: int
    endpoint_count: int
    warnings: list[str] = field(default_factory=list)


class MarkdownEndpointParser:
    def parse(self, markdown_text: str) -> MarkdownEndpointParseResult:
        normalized = markdown_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return MarkdownEndpointParseResult(sections=[], section_count=0, endpoint_count=0, warnings=["Markdown is empty."])

        sections = self._split_sections(normalized)
        endpoint_sections = [section for section in sections if section.endpoints]
        endpoint_count = sum(len(section.endpoints) for section in sections)
        warnings: list[str] = []
        if not endpoint_sections:
            warnings.append("No explicit HTTP method + path pattern was found. The full document will be sent to AI.")
            endpoint_sections = [MarkdownEndpointSection(title="Full Document", content=normalized, chunk_index=0, endpoints=[])]

        return MarkdownEndpointParseResult(
            sections=endpoint_sections,
            section_count=len(sections),
            endpoint_count=endpoint_count,
            warnings=warnings,
        )

    def _split_sections(self, markdown_text: str) -> list[MarkdownEndpointSection]:
        heading_matches = list(_HEADING_PATTERN.finditer(markdown_text))
        if not heading_matches:
            return [self._build_section(title="Document", content=markdown_text, chunk_index=0, line_start=1)]

        sections: list[MarkdownEndpointSection] = []
        for index, match in enumerate(heading_matches):
            start = match.start()
            end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(markdown_text)
            section_text = markdown_text[start:end].strip()
            title = match.group(2).strip() or f"Section {index + 1}"
            line_start = markdown_text[:start].count("\n") + 1
            sections.append(self._build_section(title=title, content=section_text, chunk_index=index, line_start=line_start))
        return sections

    def _build_section(self, *, title: str, content: str, chunk_index: int, line_start: int) -> MarkdownEndpointSection:
        endpoint_matches: list[MarkdownEndpointMatch] = []
        for match in _ENDPOINT_PATTERN.finditer(content):
            method = str(match.group(1)).upper()
            path = str(match.group(2)).strip()
            line_number = line_start + content[: match.start()].count("\n")
            endpoint_matches.append(
                MarkdownEndpointMatch(
                    method=method,
                    path=path,
                    line_number=line_number,
                    char_start=match.start(),
                    char_end=match.end(),
                )
            )
        endpoints = [f"{match.method} {match.path}" for match in endpoint_matches]
        line_end = line_start + content.count("\n")
        return MarkdownEndpointSection(
            title=title,
            content=content,
            chunk_index=chunk_index,
            endpoints=endpoints,
            endpoint_matches=endpoint_matches,
            line_start=line_start,
            line_end=line_end,
        )
