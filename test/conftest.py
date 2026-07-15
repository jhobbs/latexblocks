"""The ported suite asserts mathnotes-era output (/mathnotes/ URLs, the
mathnotes macro set). Configure once per session; content_dir stays the
relative default "content" because several tests chdir into tempdirs that
create their own content/ tree."""
import latexblocks


def pytest_configure(config):
    latexblocks.configure(url_prefix="/mathnotes")
