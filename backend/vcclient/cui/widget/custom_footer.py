from textual.app import RenderResult
from textual.widgets import Footer


class CustomFooter(Footer):
    def render(self) -> RenderResult:
        if not hasattr(self, "_key_text"):
            if hasattr(self, "_make_key_text"):
                self._key_text = self._make_key_text()
            else:
                return super().render()
        elif self._key_text is None:
            if hasattr(self, "_make_key_text"):
                self._key_text = self._make_key_text()
            else:
                return super().render()
        return self._key_text
