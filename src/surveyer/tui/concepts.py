"""In-dashboard editor for search and filter concept blocks."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Static

from surveyer.tui.config_io import ConceptItem


class ConceptRow(Horizontal):
    """One editable concept: name input, synonyms input, and delete button."""

    def __init__(self, section: str, name: str = "", synonyms: str = "") -> None:
        """Store the section this row belongs to and its initial values."""
        super().__init__(classes="concept-row")
        self._section = section
        self._name = name
        self._synonyms = synonyms

    def compose(self) -> ComposeResult:
        """Render the name input, synonyms input, and delete button."""
        yield Input(value=self._name, placeholder="concept", classes="concept-name")
        yield Input(
            value=self._synonyms,
            placeholder="synonym, synonym, ...",
            classes="concept-syn",
        )
        yield Button("✕", variant="error", classes="concept-del")

    def to_item(self) -> ConceptItem | None:
        """Read live values into a ConceptItem, or None if the name is blank."""
        name = self.query_one(".concept-name", Input).value.strip()
        if not name:
            return None
        raw = self.query_one(".concept-syn", Input).value
        synonyms = [s.strip() for s in raw.split(",") if s.strip()]
        return ConceptItem(name=name, synonyms=synonyms)


class ConceptsEditor(VerticalScroll):
    """Two-section editor (search then filter) for concept blocks."""

    def __init__(
        self,
        search: list[ConceptItem],
        filter_: list[ConceptItem],
        **kwargs,
    ) -> None:
        """Seed filter from search when search has concepts but filter does not."""
        super().__init__(**kwargs)
        self._search = list(search)
        self._filter = self._seeded_filter(self._search, filter_)

    @staticmethod
    def _seeded_filter(
        search: list[ConceptItem], filter_: list[ConceptItem]
    ) -> list[ConceptItem]:
        """Return filter, or a deep copy of search when filter is empty."""
        if search and not filter_:
            return [ConceptItem(name=c.name, synonyms=list(c.synonyms)) for c in search]
        return list(filter_)

    def compose(self) -> ComposeResult:
        """Render the search section, the filter section, and the back button."""
        yield Static("Search (fetching) concepts", classes="ce-title")
        with Vertical(id="search-rows"):
            for item in self._search:
                yield ConceptRow("search", item.name, ", ".join(item.synonyms))
        with Horizontal(classes="ce-actions"):
            yield Button("+ Add concept", id="add-search")

        yield Static("Filter (screening) concepts", classes="ce-title")
        with Vertical(id="filter-rows"):
            for item in self._filter:
                yield ConceptRow("filter", item.name, ", ".join(item.synonyms))
        with Horizontal(classes="ce-actions"):
            yield Button("+ Add concept", id="add-filter")
            yield Button("Copy from search", id="copy-search")

        yield Static(
            "Duplicate names within a section: the last one wins.",
            classes="ce-hint",
        )
        with Horizontal(classes="ce-actions"):
            yield Button("◂ Back", id="concepts-back")
            yield Button("⟲ Reset to saved", id="reset-concepts")

    def read(self, section: str) -> list[ConceptItem]:
        """Read the live rows of a section (search or filter) into ConceptItems."""
        container = "search-rows" if section == "search" else "filter-rows"
        items: list[ConceptItem] = []
        for row in self.query_one(f"#{container}").query(ConceptRow):
            item = row.to_item()
            if item is not None:
                items.append(item)
        return items

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle structural buttons; let 'concepts-back' bubble to the dashboard."""
        bid = event.button.id
        if bid == "add-search":
            self.query_one("#search-rows").mount(ConceptRow("search"))
            self.query_one("#filter-rows").mount(ConceptRow("filter"))
            event.stop()
        elif bid == "add-filter":
            self.query_one("#filter-rows").mount(ConceptRow("filter"))
            event.stop()
        elif bid == "copy-search":
            self._copy_search_to_filter()
            event.stop()
        elif event.button.has_class("concept-del"):
            row = event.button.parent
            if isinstance(row, ConceptRow):
                row.remove()
            event.stop()

    def _copy_search_to_filter(self) -> None:
        """Replace all filter rows with a fresh copy of the current search rows."""
        items = self.read("search")
        container = self.query_one("#filter-rows")
        container.remove_children()
        for item in items:
            container.mount(ConceptRow("filter", item.name, ", ".join(item.synonyms)))

    def reset(self, search: list[ConceptItem], filter_: list[ConceptItem]) -> None:
        """Rebuild both sections from the given lists, discarding unsaved edits."""
        self._search = list(search)
        self._filter = self._seeded_filter(self._search, filter_)
        for container, items in (
            ("#search-rows", self._search),
            ("#filter-rows", self._filter),
        ):
            box = self.query_one(container)
            box.remove_children()
            for item in items:
                section = "search" if container == "#search-rows" else "filter"
                box.mount(ConceptRow(section, item.name, ", ".join(item.synonyms)))
