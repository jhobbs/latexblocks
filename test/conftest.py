"""The ported suite asserts mathnotes-era output (/mathnotes/ URLs, the
mathnotes macro set). Configure once per session; content_dir stays the
relative default "content" because several tests chdir into tempdirs that
create their own content/ tree. node_modules_dir is pinned to the cwd at
session start (the repo root, which has node_modules/mathjax) because the
MathML worker otherwise resolves mathjax from its own cwd, which chdir'd
tests would leave pointed at a tempdir with no node_modules."""
import os

import latexblocks


def pytest_configure(config):
    latexblocks.configure(url_prefix="/mathnotes", node_modules_dir=os.getcwd())


class DictUrlMapper:
    """Minimal latexblocks.mapper.UrlMapper for tests: canonical URL -> path."""
    def __init__(self, mapping):
        self.url_mappings = dict(mapping)
        self._reverse = {v: k for k, v in self.url_mappings.items()}

    def get_canonical_url(self, file_path):
        return self._reverse[file_path.replace("\\", "/")]
