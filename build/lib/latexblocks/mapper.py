"""The URL-mapper protocol every latexblocks consumer implements.

block_index and page_renderer call get_canonical_url(file_path); ref_resolver
iterates url_mappings (canonical URL -> file path) to resolve bare \\pagelink
slugs. mathnotes provides ContentDiscovery; a single-page consumer can be as
small as a two-method class over a one-entry dict.
"""
from typing import Dict, Protocol


class UrlMapper(Protocol):
    url_mappings: Dict[str, str]

    def get_canonical_url(self, file_path: str) -> str: ...
